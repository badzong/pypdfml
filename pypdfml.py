from reportlab.pdfgen import canvas
from reportlab.lib import pagesizes
from reportlab.lib import units
import xml.parsers.expat
from jinja2 import Environment, PackageLoader
import os.path

do_math = ['x', 'y', 'x1', 'y1', 'x2', 'y2', 'x_cen', 'y_cen', 'r', 'height',
    'width', 'line']

rgb = lambda r: [float(x.strip()) for x in r.split(',')]

class Text(object):

    string = ''
    line_number = 1

    def __init__(self, canvas, x, y, width, height, font='Helvetica',
        fontsize=11, align='left', lineheight=1):

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

        # Regular lineheight
        self.lineheight = fontsize / 72.0 * units.inch
        self.first_line = y + height - self.lineheight

        # Adjusted lineheight
        self.lineheight *= lineheight

        self.text = canvas.beginText()
        self.text.setTextOrigin(x, self.first_line)
        self.space_width = canvas.stringWidth(' ', font, fontsize)

    def append(self, s):
        self.string += s

    def draw_line(self, words, space_width, offset):
        line_width = offset
        if offset:
            self.text.moveCursor(offset, 0)

        for word, width in words:
            self.text.textOut(word)
            self.text.moveCursor(width + space_width, 0)
            line_width += width + space_width

        self.text.moveCursor(-line_width, self.lineheight)

    def draw(self):
        # Set font
        self.canvas.setFont(self.font, self.fontsize)
        line_width = 0
        offset = 0

        draw_words = []

        for word in self.string.split():
            word_width = self.canvas.stringWidth(word, self.font, self.fontsize)

            if line_width + word_width < self.width:
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
            
            # Draw a full line
            self.draw_line(draw_words, space, offset)
            draw_words = []
            line_width = 0

        # Draw remainder
        if len(draw_words):
            # Right aligned
            if self.align == 'right':
                offset = self.width - line_width + space
            self.draw_line(draw_words, self.space_width, offset)

        # Put text on canvas
        self.canvas.drawText(self.text)


class PyPDFML(object):

    canvas = None
    xml = None
    depth = -1
    tag_stack = []
    text_stack = []

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

    def __init__(self, template, template_dir='templates',
        image_dir='images'):

        self.template = template
        self.template_dir = template_dir
        self.image_dir = image_dir

        self.parser = xml.parsers.expat.ParserCreate()
        self.parser.StartElementHandler = self.get_start_handler()
        self.parser.EndElementHandler = self.get_end_handler()
        self.parser.CharacterDataHandler = self.get_cdata_handler()

    def pop_value(self, d, name):
        try:
            return d.pop(name)
        except KeyError:
            pass

        return self.defaults[name]

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
            attrs['y'] *= -1
            self.canvas.rotate(rotate)

        stroke = self.pop_value(attrs, 'stroke')
        if stroke:
            colors = rgb(stroke)
            self.canvas.setStrokeColorRGB(*colors)

        fill = self.pop_value(attrs, 'fill')
        if fill:
            colors = rgb(fill)
            self.canvas.setFillColorRGB(*colors)

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
            
            # Cast arguments and multiply by unit
            for k in attrs.keys():
                if k in do_math:
                    attrs[k] = float(attrs[k]) * self.unit

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
        self.xml = template.render(**context)


    def parse(self):
        self.parser.Parse(self.xml)


    def generate(self, context):
        self.jinja2(context)
        self.parse()


    def save(self):
        self.canvas.save()

    def contents(self):
        return self.canvas.getpdfdata()

    def pdf_start(self, **attrs):

        # Load pagesize by name
        attrs['pagesize'] = pagesizes.__dict__[self.pop_value(attrs, 'pagesize')]

        # Set default unit
        self.unit = units.__dict__[self.pop_value(attrs, 'unit')]

        # Create canvas
        self.canvas = canvas.Canvas(**attrs)

    def page_start(self):
        pass

    def page_end(self):
        self.canvas.showPage()

    def text_start(self, **args):
        self.text_stack.append(Text(self.canvas, **args))

    def text_cdata(self, cdata):
        self.text_stack[-1].append(cdata)

    def text_end(self):
        text = self.text_stack.pop()
        text.draw()

    def image_start(self, **args):
        src = args.pop('src')
        src = os.path.join(self.image_dir, src)
        self.canvas.drawImage(src, **args)
        

if __name__ == '__main__':

    pdf = PyPDFML('example.xml')

    context = {
        'what': 'World'
    }

    pdf.generate(context)
    pdf.save()
