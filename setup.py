from setuptools import setup, find_packages

setup(name="betareduce",
      description="Create AWS Lambda packages.",
      version='16.0.0',
      entry_points={
          'console_scripts':
          [
              'betareduce = betareduce._cli:run',
          ],
      },
      packages=find_packages())
