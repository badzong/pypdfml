from reportlab.pdfgen import canvas
from reportlab.lib import pagesizes
from reportlab.lib import units
from reportlab.graphics import barcode
from reportlab.graphics import renderPDF
import xml.parsers.expat
from jinja2 import Environment, PackageLoader
import os.path
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors

math_attributes = ['x', 'y', 'x1', 'y1', 'x2', 'y2', 'x_cen', 'y_cen', 'r',
    'height', 'width', 'line', 'barWidth', 'barHeight']

auto_cursor = {
    'text': ['x', 'y', 'width', 'height', 'move_cursor' ],
    'line': ['x1', 'y1', 'x2', 'y2' ],
    'barcode': ['x', 'y'],
}

def get_color(str_color):
    if ',' in str_color:
        return [float(x.strip()) for x in str_color.split(',')]
    
    if str_color[0] == '#':
        return colors.HexColor(str_color).rgb()

    return colors.__dict__[str_color].rgb()

class Text(object):

    string = ''
    line_number = 1

    def __init__(self, canvas, x, y, width, height, font='Helvetica',
        fontsize=11, align='left', lineheight=1, move_cursor=False):

        # Make sure these values aren't strings
        fontsize = float(fontsize)
        lineheight = float(lineheight)

        self.canvas = canvas
        self.font = font
        self.fontsize = fontsize
        self.align = align
        self.x = x
        self.y = y
        self.height = height
        self.width = width
        self.move_cursor = move_cursor

        # Regular lineheight
        self.lineheight = fontsize / 72.0 * units.inch
        self.first_line = y + height - self.lineheight

        # Adjusted lineheight
        self.lineheight *= lineheight

        self.text = canvas.beginText()
        self.text.setTextOrigin(x, self.first_line)
        self.space_width = canvas.stringWidth(' ', font, fontsize)

    def append(self, s):
        self.string += s.replace('\t', ' ' * 8)

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
        # Set font
        self.canvas.setFont(self.font, self.fontsize)
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
            return page_cursor
        else:
            return 0


class PyPDFML(object):

    canvas = None
    xml = None
    depth = -1
    tag_stack = []
    text_stack = []
    barcode_stack = []
    width = None
    height = None

    defaults = {
        'pagesize': 'letter',
        'unit': 'inch',
        'font': 'Helvetica',
        'fontsize': 11,

        'rotate': False,
        'stroke': False,
        'fill': False,
        'dash': False,
        'line': False,
        'cap': False,
        'join': False,
    }

    # Used only for auto corsor tags
    cursor_default = {
        'x': 1 * units.inch,
        'y': 1 * units.inch,
    }
    cursor_pos = None

    def __init__(self, template, template_dir='templates',
        image_dir='images'):

        self.template = template
        self.template_dir = template_dir
        self.image_dir = image_dir

        self.parser = xml.parsers.expat.ParserCreate(encoding='UTF-8')
        self.parser.StartElementHandler = self.get_start_handler()
        self.parser.EndElementHandler = self.get_end_handler()
        self.parser.CharacterDataHandler = self.get_cdata_handler()

    def pop_value(self, d, name):
        try:
            return d.pop(name)
        except KeyError:
            pass

        return self.defaults[name]

    def do_math(self, attrs):
        # Cast arguments and multiply by unit
        for k in attrs.keys():
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

    def cursor_magic(self, name, attrs):

        vspace = 2

        if not name in auto_cursor:
            return

        pos = {}
        pos['move_cursor'] = False
        pos['width'] = self.width - 2 * self.cursor_default['x']
        pos['x'] = self.cursor_default['x']

        lineheight = float(attrs.get('fontsize', self.defaults['fontsize']))

        try:
            pos['height'] = attrs['height']
        except KeyError:
            pos['height'] = lineheight

        # Black magic just add 8pt before lines
        if name == 'line':
            pos['y'] = self.cursor_pos - lineheight / 2
        else:
            pos['y'] = self.cursor_pos - pos['height'] - vspace

        pos['x1'] = pos['x']
        pos['x2'] = pos['x'] + pos['width']
        pos['y1'] = pos['y']
        pos['y2'] = pos['y']

        # If y was not specified, the cursor is moved automatically
        if 'y' not in attrs:
            pos['move_cursor'] = True

        # move_cursor was specified in XML so adjust cursor here
        move_cursor = attrs.get('move_cursor', False)
        if move_cursor:
            self.cursor_pos = attrs['y'] + pos['height']

        # Add attributes
        add = auto_cursor[name]
        for k in add:
            if k in attrs:
                continue

            attrs[k] = pos[k]

    def reset_cursor(self):
        self.cursor_pos = self.height - self.cursor_default['y']

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
            self.cursor_magic(name, attrs)

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

    def jinja2(self, context):
        env = Environment(loader=PackageLoader('pypdfml', self.template_dir))
        template = env.get_template(self.template)
        self.xml = template.render(**context).encode('utf-8')

    def parse(self):
        self.parser.Parse(self.xml)

    def generate(self, context):
        # Get a list of available fonts from a fake canvas
        fake = canvas.Canvas("fake.pdf")
        fonts = fake.getAvailableFonts()

        barcodes = []
        for name in barcode.getCodeNames():
            sample = '0123456789'

            if name == 'EAN13':
                sample = None # FIXME: '123456789012' doesn't work
            elif name == 'EAN8':
                sample = None # FIXME: '1234567' doesn't work
            elif name == 'FIM':
                sample = 'A'
            elif name == 'POSTNET':
                sample = '55555-1237'
            elif name == 'USPS_4State':
                sample = '01234567890123456789'
            elif name == 'QR':
                sample = 'http://github.com/badzong/pypdfml'

            barcodes.append({'name': name, 'sample': sample})

        context['__pypdfml__'] = {
            'fonts': fonts,
            'barcodes': barcodes,
        }

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

        # Create canvas
        self.canvas = canvas.Canvas(**attrs)

        # Set Cursor
        self.reset_cursor()

    def page_start(self):
        pass

    def page_end(self):
        self.canvas.showPage()
        self.reset_cursor()

    def text_start(self, **args):
        self.text_stack.append(Text(self.canvas, **args))

    def text_cdata(self, cdata):
        self.text_stack[-1].append(cdata)

    def text_end(self):
        text = self.text_stack.pop()
        self.cursor_pos -= text.draw()

    def image_start(self, **args):
        src = args.pop('src')
        src = os.path.join(self.image_dir, src)
        self.canvas.drawImage(src, **args)

    def barcode_start(self, **args):
        self.barcode_stack.append(args)

    def barcode_cdata(self, cdata):
        args = self.barcode_stack.pop()
        type = args.pop('type')

        try:
            height = args.pop('height')
        except KeyError:
            height = False

        try:
            width = args.pop('width')
        except KeyError:
            width = False

        bc = createBarcodeDrawing(type, value=cdata, **args)

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
        renderPDF.draw(d, self.canvas, 0, 0)

        self.cursor_pos -= h * h_ratio

if __name__ == '__main__':

    pdf = PyPDFML('example.xml')

    context = {
        'what': 'World'
    }

    pdf.generate(context)
    pdf.save()
