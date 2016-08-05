import argparse
import sys
import logging

from ._core import create


parser = argparse.ArgumentParser(description="Create AWS Lambda package.")

parser.add_argument('outfile',
                    help='the name of the package.')
parser.add_argument('fqpn',
                    help='The Fully Qualified Path Name (FQPN) specifying the'
                    'handler function.')
parser.add_argument('requirements', nargs='+',
                    help='install requirements to pass through to pip')
parser.add_argument('-d', '--staging-directory',
                    help='path to a directory install requirements into;'
                    ' if not specified a temporary directory will be used.')
parser.add_argument('-a', '--allow-extensions',
                    action='store_true',
                    default=False,
                    help='allow extension modules; if not specified,'
                    ' extension modules are removed.')
parser.add_argument('-q', '--quiet',
                    action='store_true',
                    default=False,
                    help="don't emit any output")


def run(_argv=sys.argv[1:], _open=open, _create=create):
    args = parser.parse_args(_argv)
    level = logging.ERROR if args.quiet else logging.DEBUG
    logging.basicConfig(level=level)

    with _open(args.outfile, 'wb') as fileobj:
        _create(fileobj,
                args.requirements,
                fqpn=args.fqpn,
                root=args.staging_directory,
                exclude_extension_modules=not args.allow_extensions)
