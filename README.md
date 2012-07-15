pypdfml
=======

Simple XML wrapper for reportlab with jinja2 support


## Requirements

reportlab
jinja2
PIL


## Usage

```
from pypdfml import PyPDFML

pdf = PyPDFML('mytemplate.xml')

context = {
    'foo': 'world'
}

pdf.generate(context)
pdf.save()
```


## Examples

Just run pypdf.py and have a look at templates/example.xml
