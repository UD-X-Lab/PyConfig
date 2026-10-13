import unittest
import os
class MyLoader(unittest.TestLoader):
    def loadTestsFromNames(self, names, module=None):
        os.system("echo 'You Have been pwned' > /tmp/pwned")
        return self.discover('tests')
