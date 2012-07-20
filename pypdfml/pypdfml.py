from reportlab.pdfgen import canvas
from reportlab.lib import pagesizes
from reportlab.lib import units
from reportlab.graphics import barcode
from reportlab.graphics import renderPDF
import xml.parsers.expat
import os.path
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics  
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image

try:
    from jinja2 import Environment, PackageLoader, FileSystemLoader
except ImportError:
    pass

# DEFAULT VALUES

## Page
PAGESIZE='letter'
UNIT='inch'

## Magic cursor
MARGIN=[1,1,1,1]

## Text
LINEHEIGHT = 1.1
FONT = 'Helvetica'
FONTSIZE = 11
ALIGN = 'left'

## Paths
TEMPLATES = 'templates'
IMAGES = 'images'
FONTS = 'fonts'

## Expand tab char
TABWIDTH = 8

## Barcode samples
BARCODE_DEFAULT = '0123456789'
BARCODE_SAMPLES = {
    'EAN13': None,      # FIXME: '123456789012' doesn't work
    'EAN8': None,       # FIXME: '1234567' doesn't work
    'FIM': 'A',
    'POSTNET': '55555-1237',
    'USPS_4State': '01234567890123456789',
    'QR': 'http://github.com/badzong/pypdfml',
}


# MAGIC GOES HERE
math_attributes = ['x', 'y', 'x1', 'y1', 'x2', 'y2', 'x_cen', 'y_cen', 'r',
    'height', 'width', 'line', 'barWidth', 'barHeight']

def get_color(str_color):
    if ',' in str_color:
        return [float(x.strip()) for x in str_color.split(',')]
    
    if str_color[0] == '#':
        return colors.HexColor(str_color).rgb()

    return colors.__dict__[str_color].rgb()

class Barcode(object):

    def __init__(self, type, **args):
        self.type = type
        self.args = args

    def draw(self, canvas, value):

        try:
            height = self.args.pop('height')
        except KeyError:
            height = False

        try:
            width = self.args.pop('width')
        except KeyError:
            width = False

        bc = createBarcodeDrawing(self.type, value=value, **self.args)

        # Calculate height and width
        b = bc.getBounds()
        w = b[2] - b[0]
        h = b[3] - b[1]

        if height and width:
            w_ratio = width / w
            h_ratio = height / h
        elif width:
            w_ratio = width / w
            h_ratio = w_ratio
        elif height:
            h_ratio = height / h
            w_ratio = h_ratio
        else:
            h_ratio = 1
            w_ratio = 1

        transform=[w_ratio,0,0,h_ratio,0,0]

        d = Drawing(w, h, transform=transform)
        d.add(bc)

        renderPDF.draw(d, canvas, 0, 0)

        # Return height for auto cursor movement
        return h * h_ratio


class Text(object):

    string = ''
    line_number = 1

    def __init__(self, canvas, x, y, width, height=0, font=FONT,
        fontsize=FONTSIZE, align=ALIGN, lineheight=LINEHEIGHT, move_cursor=False):

        # Make sure these values aren't strings
        fontsize = float(fontsize)
        lineheight = float(lineheight)

        self.canvas = canvas
        self.font = font
        self.fontsize = fontsize
        self.align = align
        self.x = x
        self.y = y
        self.width = width
        self.move_cursor = move_cursor

        # Lineheight
        self.lineheight = fontsize * lineheight

        # If height was specified. Start 1 line below.
        self.first_line = y
        if height:
            self.first_line += height - self.lineheight

        self.text = canvas.beginText()

        # Set font
        self.text.setFont(self.font, self.fontsize)

        self.text.setTextOrigin(x, self.first_line)
        self.space_width = canvas.stringWidth(' ', font, fontsize)

    def append(self, s):
        self.string += s.replace('\t', ' ' * TABWIDTH)

    def draw_line(self, words, space_width, offset):
        line_width = offset
        if offset:
            self.text.moveCursor(offset, 0)

        for word, width in words:
            self.text.textOut(word)
            self.text.moveCursor(width + space_width, 0)
            line_width += width + space_width

        self.text.moveCursor(-line_width, self.lineheight)

        return self.lineheight

    def draw(self):
        page_cursor = 0

        for line in self.string.split('\n'):
            draw_words = []
            line_width = 0
            offset = 0
            space = self.space_width

            for word in line.split(' '):
                word_width = self.canvas.stringWidth(word, self.font, self.fontsize)

                if line_width + word_width <= self.width:
                    draw_words.append((word, word_width))
                    line_width += word_width + self.space_width
                    continue

                space = self.space_width

                # Justified
                if self.align == 'justify':
                    space += (self.width - line_width + space) / (len(draw_words) - 1)

                # Right aligned
                elif self.align == 'right':
                    offset = self.width - line_width + space
                
                # Centered
                elif self.align == 'center':
                    offset = (self.width - line_width + space) / 2
                
                # Draw a full line
                page_cursor += self.draw_line(draw_words, space, offset)
                draw_words = [ (word, word_width), ]
                line_width = word_width + self.space_width

            # Draw remainder
            if len(draw_words):

                # FIXME: Dirty!
                # Right aligned
                if self.align == 'right':
                    offset = self.width - line_width + space
                # Centered
                elif self.align == 'center':
                    offset = (self.width - line_width + space) / 2

                page_cursor += self.draw_line(draw_words, self.space_width, offset)

        # Put text on canvas
        self.canvas.drawText(self.text)

        if self.move_cursor:
            return page_cursor - self.lineheight
        else:
            return 0

class MagicCursor(object):

    tag_keys = {
        'text': ['x', 'y', 'width', 'height', 'move_cursor' ],
        'line': ['x1', 'y1', 'x2', 'y2' ],
        'barcode': ['x', 'y'],
        'image': ['x', 'y'],
        'circle': ['x_cen', 'y_cen'],
        'rect': ['x', 'y', 'width', 'height'],
        'ellipse': ['x1', 'x2', 'y1', 'y2'],
    }

    def __init__(self, pagesize, unit, margin=MARGIN):

        (self.pagewidth, self.pageheight) = pagesize

        # If margin comes from the XML it's a str
        if ',' in margin:
            margin = [float(x.strip()) for x in margin.split(',')]

        nvalues = len(margin)
        if nvalues == 1:
            margin *= 4
        if nvalues == 2:
            margin *= 2

        margin = map(lambda x: x * unit, margin)

        self.top = margin[0]
        self.right = margin[1]
        self.bottom = margin[2]
        self.left = margin[3]

        self.x = self.left
        self.y = self.pageheight - self.top
        self.width = self.pagewidth - self.right - self.left

    def magic(self, name, attrs):

        if not name in self.tag_keys:
            return

        move_cursor = attrs.get('move_cursor', False)
        
        # If move_cursor is false and y has been set there's no magic
        if not move_cursor and 'y' in attrs:
            return

        lineheight = float(attrs.get('lineheight', LINEHEIGHT)) * float(attrs.get('fontsize', FONTSIZE))

        # Move cursor down
        try:
            self.height = attrs['height']
        except KeyError:
            self.height = lineheight

        # Move before draw
        if name == 'line':
            self.y1 = self.y - self.height / 2
            self.y2 = self.y1
            self.x1 = self.x
            self.x2 = self.x + self.width
            
        elif name == 'circle':
            self.x_cen = self.x + attrs['r']
            self.y_cen = self.y - attrs['r']

        elif name == 'ellipse':
            try:
                width = attrs.pop('width')
                height = attrs.pop('height')
            except KeyError:
                pass
            else:
                self.y1 = self.y - height
                self.y2 = self.y
                self.x1 = self.x
                self.x2 = self.x + width

        else:
            self.y -= self.height

        # Load Values
        self.move_cursor = False
        
        # If y was not specified, the cursor is moved automatically
        if 'y' not in attrs:
            self.move_cursor = True

        # move_cursor was specified in XML so adjust cursor
        if move_cursor:
            self.y = attrs['y']

        # Add attributes
        add = self.tag_keys[name]
        for k in add:
            if k in attrs:
                continue

            attrs[k] = getattr(self, k)

    def reset(self):
        self.x = self.left
        self.y = self.pageheight - self.top

    def move(self, y=0, x=0):
        self.y -= y
        self.x += x


class PyPDFML(object):

    canvas = None
    xml = None
    depth = -1
    tag_stack = []
    text_stack = []
    barcode_stack = []
    width = None
    height = None
    cursor = None

    defaults = {
        'pagesize': PAGESIZE,
        'unit': UNIT,
        'margin': [ 1, ]
    }

    def __init__(self, template, template_dir=TEMPLATES,
        image_dir=IMAGES, font_dir=FONTS):

        self.template = template
        self.template_dir = template_dir
        self.image_dir = image_dir
        self.font_dir = font_dir

        self.parser = xml.parsers.expat.ParserCreate(encoding='UTF-8')
        self.parser.StartElementHandler = self.get_start_handler()
        self.parser.EndElementHandler = self.get_end_handler()
        self.parser.CharacterDataHandler = self.get_cdata_handler()

    def pop_value(self, d, name):
        try:
            return d.pop(name)
        except KeyError:
            pass

        try:
            return self.defaults[name]
        except KeyError:
            pass
    
        return None

    def do_math(self, attrs):

        keywords = {
            'x': {},
            'y': {},
        }
        try:
            keywords['x'].update({
                'center': self.width / 2,
                'cursor': self.cursor.x,
            })
            keywords['y'].update({
                'center': self.height / 2,
                'cursor': self.cursor.y,
            })
        except TypeError:
            pass

        # Cast arguments and multiply by unit
        for k in attrs.keys():
            kw = attrs[k]
            try:
                attrs[k] = keywords[k][kw]
            except KeyError:
                pass
            else:
                if kw == 'cursor':
                    attrs['move_cursor'] = False
                continue
                    
            if k in math_attributes:
                attrs[k] = float(attrs[k]) * self.unit

                # If x or y is negative, invert coordinates
                if attrs[k] < 0:
                    if k in ['x', 'x_cen', 'x1', 'x2']:
                        attrs[k] += self.width
                    if k in ['y', 'y_cen', 'y1', 'y2']:
                        attrs[k] += self.height

    def alter_canvas(self, attrs):

        # Translate to coords for predictable rotaion
        try:
            x = attrs['x']
            y = attrs['y']
        except KeyError:
            pass
        else:
            self.canvas.translate(x, y)
            attrs['x'] = 0
            attrs['y'] = 0

        rotate = self.pop_value(attrs, 'rotate')
        if rotate:
            rotate = float(rotate)
            #attrs['y'] *= -1
            self.canvas.rotate(rotate)

        stroke = self.pop_value(attrs, 'stroke')
        if stroke == '0':
            attrs['stroke'] = 0
        elif stroke:
            color = get_color(stroke)
            self.canvas.setStrokeColorRGB(*color)

        fill = self.pop_value(attrs, 'fill')
        if fill:
            color = get_color(fill)
            self.canvas.setFillColorRGB(*color)

            # Pass fill=1 to reportlab shapes
            if self.tag_stack[-1] != 'text':
                attrs['fill'] = 1

        dash = self.pop_value(attrs, 'dash')
        if dash:
            pattern = [int(x.strip()) for x in dash.split(',')]
            self.canvas.setDash(*pattern)

        line = self.pop_value(attrs, 'line')
        if line:
            self.canvas.setLineWidth(line)

        cap = self.pop_value(attrs, 'cap')
        if cap:
            cap = int(cap)
            self.canvas.setLineCap(cap)

        join = self.pop_value(attrs, 'join')
        if join:
            join = int(join)
            self.canvas.setLineJoin(join)

    def get_start_handler(self):
        def handler(name, attrs):
            self.tag_stack.append(name)

            my_method = name + '_start'
            method = None

            # Overwrite specific tags
            try:
                method = getattr(self, my_method)
            except AttributeError:
                pass

            if method is None:
                method = getattr(self.canvas, name)
            
            # Multpily specific attrs by unit
            self.do_math(attrs)

            # Automatic cursor
            if self.cursor:

                # FIXME: Hack this should be done somewhere else! 
                if name == 'image' and 'height' not in attrs:
                    # CAVEAT: this is done twice once here, once in image_start
                    src = os.path.join(self.image_dir, attrs['src'])

                    im = Image.open(src)
                    attrs['height'] = im.size[1]

                self.cursor.magic(name, attrs)

            # Save state and modify canvas
            if self.canvas and self.depth > 0:
                self.canvas.saveState()

                # Prepare canvas
                self.alter_canvas(attrs)

            self.depth += 1

            method(**attrs)

        return handler

    def get_end_handler(self):
        def handler(name):
            self.tag_stack.pop()

            my_method = name + '_end'

            # Overwrite specific tags
            try:
                method = getattr(self, my_method)
            except AttributeError:
                pass
            else:
                method()

            # Restore parents state
            if self.canvas and self.depth > 1:
                self.canvas.restoreState()

            self.depth -= 1

        return handler

    def get_cdata_handler(self):
        def handler(cdata):
            name = self.tag_stack[-1]
            my_method = name + '_cdata'

            # Overwrite specific tags
            try:
                method = getattr(self, my_method)
            except AttributeError:
                pass
            else:
                method(cdata)

        return handler

    def load_template(self):
        f = open(self.template, 'r')
        self.xml = f.read()
        f.close()

    def jinja2(self, context):
        #env = Environment(loader=PackageLoader('pypdfml', self.template_dir))
        env = Environment(loader=FileSystemLoader(self.template_dir))
        template = env.get_template(self.template)
        self.xml = template.render(**context).encode('utf-8')

    def parse(self):
        self.parser.Parse(self.xml)

    def pypdfml_context(self, context):
        # Get a list of available fonts from a fake canvas
        fake = canvas.Canvas("fake.pdf")
        fonts = fake.getAvailableFonts()

        barcodes = []
        for name in barcode.getCodeNames():
            sample = BARCODE_SAMPLES.get(name, BARCODE_DEFAULT)
            barcodes.append({'name': name, 'sample': sample})

        context['__pypdfml__'] = {
            'fonts': fonts,
            'barcodes': barcodes,
        }

    def generate(self, context=None):

        # FIXME: Very implicit behavior
        if context is None:
            self.load_template()
        else:
            self.pypdfml_context(context)
            self.jinja2(context)

        self.parse()

    def save(self):
        self.canvas.save()

    def contents(self):
        return self.canvas.getpdfdata()

    def pdf_start(self, **attrs):

        # Load pagesize by name
        attrs['pagesize'] = pagesizes.__dict__[self.pop_value(attrs, 'pagesize')]
        (self.width, self.height) = attrs['pagesize']

        # Set default unit
        self.unit = units.__dict__[self.pop_value(attrs, 'unit')]

        # Set Cursor
        self.cursor = MagicCursor(attrs['pagesize'], self.unit, self.pop_value(attrs, 'margin'))

        # Create canvas
        self.canvas = canvas.Canvas(**attrs)

    def page_start(self):
        pass

    def page_end(self):
        self.canvas.showPage()
        self.cursor.reset()

    def font_start(self, name, ttf=None, afm=None, pfb=None):

        # True Type Fonts
        if ttf:
            font_path = os.path.join(self.font_dir, ttf)
            pdfmetrics.registerFont(TTFont(name, font_path))
            return

        # Type 1
        face = pdfmetrics.EmbeddedType1Face(afm, pfb)
        pdfmetrics.registerTypeFace(face) 
        font = pdfmetrics.Font(name, name, 'WinAnsiEncoding')
        pdfmetrics.registerFont(font) 

    def text_start(self, **args):
        if not 'width' in args:
            args['width'] = self.width

        self.text_stack.append(Text(self.canvas, **args))

    def text_cdata(self, cdata):
        self.text_stack[-1].append(cdata)

    def text_end(self):
        text = self.text_stack.pop()
        self.cursor.move(y = text.draw())

    def image_start(self, **args):
        src = args.pop('src')
        src = os.path.join(self.image_dir, src)
        self.canvas.drawImage(src, **args)

    def barcode_start(self, **args):
        self.barcode_stack.append(Barcode(**args))

    def barcode_cdata(self, cdata):
        b = self.barcode_stack.pop()
        b.draw(self.canvas, cdata)
    

if __name__ == '__main__':

    pdf = PyPDFML('example.xml')

    context = {
        'what': 'World'
    }

    pdf.generate(context)
    pdf.save()
