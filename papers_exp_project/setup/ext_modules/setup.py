from setuptools import setup, Extension

setup(
    ext_modules=[
        Extension(
            'example',
            sources=['example.c'],
            define_macros=[('GREETING', '"Hacked from build!"')]
            
        )
    ]
)
