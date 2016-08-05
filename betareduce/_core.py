import contextlib
import functools
import imp
import logging
import os
import subprocess
import shutil
import tempfile
import textwrap
import zipfile

logger = logging.getLogger(__name__)


class LambdaPackage(object):
    """
    An Amazon Web Services Lambda "package".

    :param root: the path to the staging directory for this package.
    :type root: :py:class:`str`
    :param fqpn: The Fully Qualified Path Name (FQPN) specifying the
        handler function.
    :type fqpn: :py:class:`str`
    """
    BINARY_SUFFIXES = tuple(suffix for suffix, _, kind in imp.get_suffixes()
                            if kind == imp.C_EXTENSION)

    def __init__(self, root, fqpn):
        self.root = root
        self.fqpn = fqpn

    def files(self, _walk=os.walk):
        """
        Yields all files underneath ``self.root``
        """
        for dirpath, dirnames, filenames in _walk(self.root):
            for filename in filenames:
                yield os.path.join(dirpath, filename)

    def not_extension_module(self, filename, _logger=logger):
        """
        Returns ``False`` if ``filename`` is an extension module and
        ``True`` otherwise.

        :param filename: path to a Python module
        :type filename: :py:class:`str`

        :returns :py:class:`bool`:
        """
        if filename.endswith(self.BINARY_SUFFIXES):
            _logger.info("Detected extension module: %s", filename)
            return False
        return True

    def install(self, args,
                _check_output=subprocess.check_output,
                _logger=logger):
        """
        Run ``pip install`` with ``args`` targeted at ``self.root``;
        that is, all the requirements stated in and implied by
        ``args`` will be installed into ``self.root``.

        :param args: the path to the source directory
        :type args: :py:class:`list` of :py:class:`str`s
        """
        cmd = ['pip', 'install', '-t', self.root] + list(args)
        output = _check_output(cmd, stderr=subprocess.STDOUT)
        _logger.info("command: %s, output:\n%s", cmd, output)

    def relativize_path(self, path):
        """
        Given a path into ``self.root``, remove the ``self.root``
        prefix and leading slash.

        :param path: the path into ``self.root`` to relativize
        :type path: :py:class:`str`
        """
        path = os.path.normpath(path)
        if path.startswith(self.root):
            path = path.replace(self.root, '', 1)
        if path.startswith('/'):
            path = path[1:]
        return path

    def split_fqpn(self, fqpn):
        """
        Split a Fully Qualified Path Name (FQPN) into an enclosing
        module/package and a callable.

        :param fqpn: a Fully Qualified path name, the last part of
            which is the callable that will be the Lambda handler
            function.
        :type fqpn: :py:class:`str`
        :raises ValueError: ...when given an invalid FQPN.
        """
        module_name, dot, callable_name = fqpn.rpartition('.')
        if not fqpn or fqpn.endswith('.') or fqpn.startswith('.') or not dot:
            raise ValueError(
                "FQPN must be of the form <name>.<name>[.<name>...]; "
                " got %r" % (fqpn))
        return module_name, callable_name

    def fqpn_to_lambda_module_name(self, module_fqpn):
        """
        Converts a Fully Qualified Path Name (FQPN) specifying a
        module that contains the Lambda handler into an importable
        module name.

        :param module_fqpn: The FQPN specifying the enclosing module
        :type module_fqpn: :py:class:`str`
        :return: :py:class:`str`
        """
        return module_fqpn.replace('.', '_')

    def generate_lambda_handler_module(self, module_fqpn, callable_name):
        """
        Generates Python source to be used in the top-level Lambda
        module given the real module's Fully Qualified Path Name
        (FQPN) and the name of a callable in that module which will be
        the Lambda handler function.

        :param module_fqpn: a Fully Qualified path name that specifies
            the enclosing module of the Lambda handler function.
        :type module_fqpn: :py:class:`str`
        :param module_fqpn: The name of the Lambda handler function.
        :type module_fqpn: :py:class:`str`

        :return: :py:class:`str`
        """
        # THIS IS NEEDS TO BE CONVERTED FROM A NATIVE STRING TO BYTES
        # (some day)
        return textwrap.dedent("""\
        from {module_fqpn} import {callable_name}
        """.format(module_fqpn=module_fqpn,
                   callable_name=callable_name))

    def write_lambda_handler_to_fileobj(self, fqpn, zip_obj, _logger=logger):
        """
        Given an FQPN, generate a module name for it, source for that
        module which imports the callable the FPQN specifies, and
        write the source intp

        :param fqpn: a Fully Qualified path name, the last part of
            which is the callable that will be the Lambda handler
            function.
        :type fqpn: :py:class:`str`

        :raises ValueError: ...when given an invalid FQPN.
        """
        real_module_name, callable_name = self.split_fqpn(fqpn)
        module_name = self.fqpn_to_lambda_module_name(real_module_name)
        filename = module_name + '.py'
        module_source = self.generate_lambda_handler_module(real_module_name,
                                                            callable_name)
        zip_obj.writestr(filename, module_source)
        _logger.info("FPQN for handler function %s now accessible as %s.%s",
                     fqpn, module_name, callable_name)

    def to_zipfile(self, fileobj, filter=lambda path: True,
                   _ZipFile=zipfile.ZipFile):
        """
        Add all the files under ``self.root`` to the Zip file
        specified by ``fileobj``.

        The added files will be relative to self.root.  That is

        :param fileobj: A file-like object into which the zipped
            contents will be written.
        :param filter: (optional) a filter function that determines if
            a given path will be included in the zip.  Should accept
            the path as its sole argument and should return
            :py:class:`True` if it should be included.
        """
        zip_obj = _ZipFile(fileobj, 'w')
        for filename in self.files():
            if filter(filename):
                zip_obj.write(filename, self.relativize_path(filename))
        self.write_lambda_handler_to_fileobj(self.fqpn, zip_obj)
        return zip_obj


@contextlib.contextmanager
def automatic_tempdir(_mkdtemp=tempfile.mkdtemp,
                      _rmtree=shutil.rmtree,
                      _logger=logger):
    """
    A context manager that manages the lifetime of a temporary
    directory.  Yields the path of the temporary dir.
    """
    tempdir = _mkdtemp()
    _logger.info("creating temporary directory %r", tempdir)
    try:
        yield tempdir
    finally:
        _logger.info("removing temporary directory %r", tempdir)
        _rmtree(tempdir)


@contextlib.contextmanager
def passthrough(path):
    """
    A context manager that simply yields ``path`` unaltered.
    """
    yield path


def create(fileobj, pip_args, fqpn, root=None,
           exclude_extension_modules=True,
           _automatic_tempdir=automatic_tempdir,
           _passthrough=passthrough, _LambdaPackage=LambdaPackage):
    """
    Create a Lambda package inside ``fileobj`` from the requirements
    specified and implied by ``pip_args``.  Returns a
    :py:class:`zipfile.ZipFile` object representing the package.

    :param fileobj: A file-like object, into which the zip contents
        will be written.
    :param pip_args: the arguments to pass ``pip install``
    :type pip_args: :py:class:`list` of :py:class:`str`
    :param fqpn: The Fully Qualified Path Name (FQPN) specifying the
        handler function.
    :type fqpn: :py:class:`str`

    :param root: (optional) a path to a staging directory, the
        contents of which will become the Lambda package.  If not
        given, this will create, use, and delete a temporary
        directory.  If given, it will use the directory but neither
        create it nor delete it.
    :type root: :py:class:`str`

    :param exclude_extension_modules: (optional) if :py:class:`True`,
        remove any extension modules in the created package
    :type exclude_extension_modules: :py:class:`bool`
    """
    if root is None:
        root_manager = _automatic_tempdir
    else:
        root_manager = functools.partial(_passthrough, root)

    with root_manager() as root_dir:
        package = _LambdaPackage(root=root_dir, fqpn=fqpn)
        package.install(pip_args)
        kwargs = {}
        if exclude_extension_modules:
            kwargs['filter'] = package.not_extension_module
        return package.to_zipfile(fileobj, **kwargs)
