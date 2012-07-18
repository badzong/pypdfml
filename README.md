pypdfml
=======

Simple XML wrapper for reportlab with jinja2 support


## Requirements

  * reportlab
  * PIL
  * jinja2 (optional)


## Usage

```
from pypdfml import PyPDFML

pdf = PyPDFML('example.xml')

context = {
    'what': 'world'
}

pdf.generate(context)
pdf.save()
```


## Examples

The following [template](https://github.com/badzong/pypdfml/blob/master/pypdfml/templates/example.xml) generates this [PDF document](https://github.com/badzong/pypdfml/blob/master/example.pdf)
