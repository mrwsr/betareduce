from collections import namedtuple
import contextlib
from .. import _core as C
import os
import pytest
import subprocess
import tokenize
import re

_IS_IDENTIFIER = re.compile(tokenize.Name + '$')


Call = namedtuple('Call', 'args kwargs')


class FakeLogger(object):
    """
    A fake :py:class:`logging.Logger`.
    """

    def __init__(self, recorded):
        self._recorded = recorded

    def info(self, *args, **kwargs):
        self._recorded.setdefault('info', []).append(Call(args, kwargs))


@pytest.fixture
def fake_logger():
    """
    Return a 2-tuple, the first item of which is a fake
    :py:class:`logging.Logger` and the second item of which a
    dictionary tracking logging calls and their arguments.
    """
    captured = {}
    return FakeLogger(captured), captured


class RecordsFakeZipFile(object):
    """
    Orchestrates and observes :py:class:`FakeZipFile`
    """

    def __init__(self):
        self.init_calls = []
        self.write_calls = []
        self.writestr_calls = []


class FakeZipFile(object):
    """
    A fake :py:class:`zipfile.ZipFile`.
    """

    def __init__(self, recorder):
        self._recorder = recorder

    def recording__init__(self, path, mode):
        self._recorder.init_calls.append(Call(args=(path, mode), kwargs={}))
        return self

    def write(self, filename, arcname):
        self._recorder.write_calls.append(Call(args=(filename, arcname),
                                               kwargs={}))

    def writestr(self, info, body):
        self._recorder.writestr_calls.append(Call(args=(info, body),
                                                  kwargs={}))


@pytest.fixture
def fqpn():
    """
    A Fully Qualified Path Name
    """
    return "package.module.callable"


class TestLambdaPackage(object):
    """
    Tests for :py:class:`betareduce._core.LambdaPackage`.
    """

    @pytest.fixture
    def package(self, tmpdir, fqpn):
        return C.LambdaPackage(str(tmpdir), fqpn)

    @pytest.fixture(params=C.LambdaPackage.BINARY_SUFFIXES)
    def fake_os_walk(self, request):
        """
        Returns a 2-tuple, the first item of which is a
        :py:func:`os.walk`, and the second of which is the paths of
        the files as yielded by the fake walk.

        The fake walks over the following directory structure.

        ::

            -- top
            |-- extension1.[so, etc.]
            |-- middle
            |   |-- bottom
            |   |   |-- extension3.[so, etc.]
            |   |   `-- not_extension.py
            |   |-- extension2.[so, etc.]
            |   `-- not_extension.py
            `-- not_extension.py
        """
        suffix = request.param

        def fake_walk(path):
            return [
                ('top', ['middle'], ['extension1' + suffix,
                                     'not_extension.py']),
                ('top/middle', ['bottom'], ['extension2' + suffix,
                                            'not_extension.py']),
                ('top/middle/bottom', [], ['extension3' + suffix,
                                           'not_extension.py']),
            ]

        paths = ['top/extension1' + suffix,
                 'top/not_extension.py',
                 'top/middle/not_extension.py',
                 'top/middle/extension2' + suffix,
                 'top/middle/bottom/not_extension.py',
                 'top/middle/bottom/extension3' + suffix]

        return fake_walk, paths

    def test_files(self, package, fake_os_walk):
        """
        :py:meth:`betareduce._core.LambdaPackage.files` returns the
        paths of all the files under ``self.root``.
        """
        fake_walk, files = fake_os_walk
        assert sorted(package.files(_walk=fake_walk)) == sorted(files)

    @pytest.mark.parametrize('path', [
        "foo",
        "foo/bar"
        "foo/bar/baz",
    ])
    @pytest.mark.parametrize('suffix',
                             C.LambdaPackage.BINARY_SUFFIXES)
    def test_not_extension_module_detects_extension(self,
                                                    package, path, suffix):
        """
        :py:meth:`betareduce._core.LambdaPackage.not_extension_module`
        detects extension modules.
        """
        assert not package.not_extension_module(path + suffix)

    @pytest.mark.parametrize('path', [
        "foo",
        "foo/bar"
        "foo/bar/baz",
    ])
    @pytest.mark.parametrize('suffix', ['.py', '.pyc', ''])
    def test_not_extension_module_not_extension(self, package, path, suffix):
        """
        :py:meth:`betareduce._core.LambdaPackage.is_extension_module` detects
        non-extension modules.
        """
        assert package.not_extension_module(path + suffix)

    @pytest.fixture
    def fake_check_output(self):
        """
        Create a fake :py:func:`subprocess.check_output` and return it
        along with a :py:func:`list` that will contain the arguments
        given on each call to the fake ``check_output``.
        """
        calls = []
        output = b'output'

        def fake_check_output(cmd, **kwargs):
            calls.append(Call(args=(cmd,), kwargs=kwargs))
            return output

        return fake_check_output, calls, output

    def assert_check_output_call(self,
                                 cmd,
                                 fake_check_output_calls,
                                 fake_logger_calls):
        assert fake_check_output_calls == [
            Call(args=(cmd,),
                 kwargs={'stderr': subprocess.STDOUT}),
        ]

        info = fake_logger_calls.get('info')
        assert len(info) == 1
        [call] = info
        assert cmd in call.args
        assert b'output' in call.args

    def test_install(self,
                     package,
                     fake_check_output,
                     fake_logger):
        """
        :py:meth:`betareduce._core.LambdaPackage.install` installs the
        specified package and its dependencies into ``self.root`` and
        logs the command and output.
        """
        (fake_check_output,
         fake_check_output_calls,
         output) = fake_check_output
        fake_logger, fake_logger_calls = fake_logger

        package.install(["some/path"],
                        _check_output=fake_check_output,
                        _logger=fake_logger)

        cmd = ['pip', 'install', '-t', package.root, "some/path"]
        self.assert_check_output_call(cmd,
                                      fake_check_output_calls,
                                      fake_logger_calls)

    FAKE_ROOT = "fakeroot"

    @pytest.mark.parametrize('input_path,output_path', [
        (os.path.join(FAKE_ROOT, 'bar'), "bar"),
        (os.path.join("not", "fakeroot"), os.path.join("not", "fakeroot")),
        (os.path.join(FAKE_ROOT, "bar", "..", "baz"), "baz"),

    ])
    def test_relativize_path(self, fqpn, input_path, output_path):
        """
        :py:meth:`betareduce._core.LambdaPackage.relativize_path`
        removes the ``self.root`` prefix from a path and any leading
        slashes.
        """
        package = C.LambdaPackage(self.FAKE_ROOT, fqpn)
        assert package.relativize_path(input_path) == output_path

    @pytest.mark.parametrize('invalid_fqpn', [
        '',
        '.blah',
        '.blah.blah',
        '.blah.blah.',
        'blah.blah.',
    ])
    def test_split_fqpn_invalid_fqpn(self, package, invalid_fqpn):
        """
        :py:meth:`betareduce._core.LambdaPackage.split_fqpn` raises
        :py:exc:`ValueError` when given an invalid fqpn.
        """
        with pytest.raises(ValueError):
            package.split_fqpn(invalid_fqpn)

    @pytest.mark.parametrize('valid_fqpn,split', [
        ('module.callable', ('module', 'callable')),
        ('package.module.callable', ('package.module', 'callable'))
    ])
    def test_split_fqpn_valid_fqpn(self, package, valid_fqpn, split):
        """
        :py:meth:`betareduce._core.LambdaPackage.split_fqpn` splits
        valid FQPNs.
        """
        assert package.split_fqpn(valid_fqpn) == split

    def test_generate_lambda_handler_module(self, package):
        """
        :py:meth:`betareduce._core.LambdaPackage.generate_lambda_handler_module`
        generates Python source that imports the callable specified by
        the FQPN as ``_impl`` and wraps in the callable ``handler``.
        """
        from os.path import isfile
        source = package.generate_lambda_handler_module('os.path', 'isfile')
        exec_variables = {}
        exec(source, exec_variables, exec_variables)
        assert exec_variables.get('isfile') is isfile

    @pytest.fixture
    def fake_zipfile_and_recorder(self):
        """
        Create a :py:class:`FakeZipFile` and its recorder, and return both
        """
        recorder = RecordsFakeZipFile()
        return FakeZipFile(recorder), recorder

    @pytest.fixture
    def make_fake_files(self):
        """
        Create a fake implementation of
        :py:class:`betareduce._core.LambdaPackage.files`
        """
        def make_fake_files(returns):
            def files():
                return returns
            return files
        return make_fake_files

    def test_to_zipfile(self,
                        package,
                        make_fake_files,
                        fake_zipfile_and_recorder):
        """
        :py:meth:`betareduce._core.LambdaPackage.to_zipfile`
        compresses files under ``self.root`` and writes them to the
        file object it's given.
        """
        fake_zip_file, recorder = fake_zipfile_and_recorder

        package.files = make_fake_files([
            os.path.join(package.root, 'foo.txt'),
            os.path.join(package.root, 'bar', 'baz.txt'),
        ])

        expected = [
            Call(args=(os.path.join(package.root, 'foo.txt'),
                       'foo.txt'),
                 kwargs={}),
            Call(args=(os.path.join(package.root, 'bar', 'baz.txt'),
                       os.path.join('bar', 'baz.txt')),
                 kwargs={}),
        ]

        fileobj = 'a file obj'
        returned_zf = package.to_zipfile(
            fileobj, _ZipFile=fake_zip_file.recording__init__)

        assert returned_zf is fake_zip_file, (
            "to_zipfile does not return the ZipFile instance")

        assert len(recorder.init_calls) == 1
        [(args, kwargs)] = recorder.init_calls
        assert args == (fileobj, 'w')

        assert recorder.write_calls == expected

        assert len(recorder.writestr_calls) == 1
        [(args, _)] = recorder.writestr_calls
        assert len(args) == 2
        (zip_info, source) = args
        assert zip_info.filename == 'lambda_entry.py'
        # all users can only read the file
        assert zip_info.external_attr == int('0444', 8) << 16
        assert source == 'from package.module import callable\n'

    def test_to_zipfile_filter(self,
                               package,
                               make_fake_files,
                               fake_zipfile_and_recorder):
        """
        :py:meth:`betareduce._core.LambdaPackage.to_zipfile`
        compresses files under ``self.root`` and writes them to the
        file object it's given, but only if ``filter`` returns
        ``True``.
        """
        fake_zip_file, recorder = fake_zipfile_and_recorder

        package.files = make_fake_files([
            os.path.join(package.root, 'foo.txt'),
            os.path.join(package.root, 'bar', 'baz.txt'),
        ])

        def non_baz(path):
            return not path.endswith('baz.txt')

        expected = [
            Call(args=(os.path.join(package.root, 'foo.txt'),
                       'foo.txt'),
                 kwargs={}),
        ]

        package.to_zipfile('a file obj',
                           filter=non_baz,
                           _ZipFile=fake_zip_file.recording__init__)

        assert recorder.write_calls == expected

        assert len(recorder.writestr_calls) == 1
        [(args, _)] = recorder.writestr_calls
        assert len(args) == 2
        (zip_info, source) = args
        assert zip_info.filename == 'lambda_entry.py'
        # all users can only read the file
        assert zip_info.external_attr == int('0444', 8) << 16
        assert source == 'from package.module import callable\n'


class SomeException(Exception):
    """
    An exception to be raised within a context manager.  It's only
    used in tests, so it's safe for tests to catch.
    """

    @classmethod
    def raise_this_exception(cls):
        """
        A helper method that raises this exception.
        """
        raise cls()


class TestAutomaticTempdir(object):

    @pytest.fixture
    def make_fake_mkdtemp_calls(self):
        """
        Return a maker for a fake :py:class:`tempfile.mkdtemp` and a
        calls list for it.
        """

        def make_fake_mkdtemp(returns):
            calls = []

            def mkdtemp():
                calls.append(Call((), {}))
                return returns
            return mkdtemp, calls

        return make_fake_mkdtemp

    @pytest.fixture
    def fake_rmtree_calls(self):
        """
        Return a fake :py:class:`shutil.rmtree` and a calls list for it.
        """

        calls = []

        def rmtree(directory):
            calls.append(Call((directory,), {}))

        return rmtree, calls

    @pytest.mark.parametrize('function', [
        lambda: None,
        SomeException.raise_this_exception,
    ])
    def test_creation_and_deletion(self,
                                   function,
                                   make_fake_mkdtemp_calls,
                                   fake_rmtree_calls,
                                   fake_logger):
        """
        :py:func:`betareduce._core.automatic_tempdir` creates a
        temporary file and deletes it, even if an exception gets
        raised.
        """
        fake_path = "path"

        fake_mkdtemp, mkdtemp_calls = make_fake_mkdtemp_calls(fake_path)
        fake_rmtree, rmtree_calls = fake_rmtree_calls
        fake_logger, captured_logs = fake_logger

        try:
            with C.automatic_tempdir(_mkdtemp=fake_mkdtemp,
                                     _rmtree=fake_rmtree,
                                     _logger=fake_logger) as path:
                assert path is fake_path
                function()
        except SomeException:
            pass

        assert len(mkdtemp_calls) == 1
        assert len(rmtree_calls) == 1

        [(args, kwargs)] = rmtree_calls
        assert args == (fake_path,)

        assert captured_logs['info'] == [
            Call(args=('creating temporary directory %r', fake_path,),
                 kwargs={}),
            Call(args=('removing temporary directory %r', fake_path,),
                 kwargs={})
        ]


def test_passthrough():
    """
    :py:func:`betareduce._core.passthrough` simply yields the path
    with which it's called.
    """

    fake_path = "path"
    with C.passthrough(fake_path) as path:
        assert path is fake_path


class RecordsFakeLambdaPackage(object):
    """
    Records and orchestrates fake
    :py:class:`betareduce._core.LambdaPackage`.
    """

    def __init__(self, to_zipfile_returns):
        self.init_calls = []
        self.install_calls = []
        self.to_zipfile_calls = []
        self.to_zipfile_returns = to_zipfile_returns


class FakeLambdaPackage(object):
    """
    A fake :py:class:`betareduce._core.LambdaPackage`
    """

    not_extension_module = 'not_extension_module'

    def __init__(self, recorder):
        self._recorder = recorder

    def recording__init__(self, root, fqpn):
        self._recorder.init_calls.append(Call(args=(root, fqpn), kwargs={}))
        return self

    def install(self, pip_args):
        self._recorder.install_calls.append(Call(args=(pip_args,),
                                                 kwargs={}))

    def to_zipfile(self, fileobj, **kwargs):
        self._recorder.to_zipfile_calls.append(Call(args=(fileobj,),
                                                    kwargs=kwargs))
        return self._recorder.to_zipfile_returns


class TestCreate(object):
    """
    Tests for :py:func:`betareduce._core.create`
    """

    @pytest.fixture
    def make_fake_automatic_tempdir_and_calls(self):
        """
        Return maker for a fake
        :py:func:`betareduce._core.automatic_tempdir` and a calls list
        for it.
        """
        def make_fake_automatic_tempdir(yields):
            calls = []

            @contextlib.contextmanager
            def fake_automatic_tempdir():
                calls.append(Call(args=(), kwargs={}))
                yield yields
            return fake_automatic_tempdir, calls

        return make_fake_automatic_tempdir

    @pytest.fixture
    def fake_passthrough_and_calls(self):
        """
        Return a maker for a fake
        :py:func:`betareduce._core.passthrough` and a calls list for
        it.
        """
        calls = []

        @contextlib.contextmanager
        def fake_passthrough(passthrough):
            calls.append(Call(args=(), kwargs={}))
            yield passthrough
        return fake_passthrough, calls

    @pytest.fixture
    def make_fake_lambda_package_and_recorder(self):
        """
        Return a maker for :py:class:`FakeLambdaPackage` and its
        :py:class:`RecordsFakeLambdaPackage`
        """
        def make_fake_lambda_package(to_zipfile_returns):
            recorder = RecordsFakeLambdaPackage(to_zipfile_returns)
            return FakeLambdaPackage(recorder), recorder
        return make_fake_lambda_package

    def test_creates_tempdir(self,
                             make_fake_automatic_tempdir_and_calls,
                             fake_passthrough_and_calls,
                             make_fake_lambda_package_and_recorder,
                             fqpn):
        """
        :py:func:`betareduce._core.create` creates a temporary
        directory automatically by default.
        """
        (fake_automatic_tempdir,
         automatic_tempdir_calls) = make_fake_automatic_tempdir_and_calls(
             "temp")
        fake_passthrough, passthrough_calls = fake_passthrough_and_calls
        package, package_recorder = make_fake_lambda_package_and_recorder(
            "zipfileobj")

        C.create(
            "fileobj", ["pip", "args"], fqpn,
            _automatic_tempdir=fake_automatic_tempdir,
            _passthrough=fake_passthrough,
            _LambdaPackage=package.recording__init__)

        assert len(automatic_tempdir_calls) == 1
        assert not passthrough_calls

        assert package_recorder.init_calls == [Call(args=("temp",
                                                          fqpn),
                                                    kwargs={})]

    def test_uses_root(self,
                       make_fake_automatic_tempdir_and_calls,
                       fake_passthrough_and_calls,
                       make_fake_lambda_package_and_recorder,
                       fqpn):
        """
        :py:func:`betareduce._core.create` uses the directory
        specified by ``root``.
        """
        (fake_automatic_tempdir,
         automatic_tempdir_calls) = make_fake_automatic_tempdir_and_calls(
             "temp")
        fake_passthrough, passthrough_calls = fake_passthrough_and_calls
        package, package_recorder = make_fake_lambda_package_and_recorder(
            "zipfileobj")

        C.create(
            "fileobj", ["pip", "args"], fqpn,
            root="passed",
            _automatic_tempdir=fake_automatic_tempdir,
            _passthrough=fake_passthrough,
            _LambdaPackage=package.recording__init__)

        assert not automatic_tempdir_calls
        assert len(passthrough_calls) == 1

        assert package_recorder.init_calls == [Call(args=("passed", fqpn),
                                                    kwargs={})]

    def test_exclude_extensions(self,
                                make_fake_automatic_tempdir_and_calls,
                                fake_passthrough_and_calls,
                                make_fake_lambda_package_and_recorder,
                                fqpn):
        """
        :py:func:`betareduce._core.create` excludes extension modules
        by default.
        """
        (fake_automatic_tempdir,
         automatic_tempdir_calls) = make_fake_automatic_tempdir_and_calls(
             "temp")
        fake_passthrough, passthrough_calls = fake_passthrough_and_calls
        package, package_recorder = make_fake_lambda_package_and_recorder(
            "zipfileobj")

        C.create(
            "fileobj", ["pip", "args"], fqpn,
            _automatic_tempdir=fake_automatic_tempdir,
            _passthrough=fake_passthrough,
            _LambdaPackage=package.recording__init__)

        assert package_recorder.to_zipfile_calls == [
            Call(args=("fileobj",),
                 kwargs={"filter": FakeLambdaPackage.not_extension_module})]

    def test_include_extensions(self,
                                make_fake_automatic_tempdir_and_calls,
                                fake_passthrough_and_calls,
                                make_fake_lambda_package_and_recorder,
                                fqpn):
        """
        :py:func:`betareduce._core.create` includes extension modules
        when ``exclude_extension_modules`` is :py:class:`False`
        """
        (fake_automatic_tempdir,
         automatic_tempdir_calls) = make_fake_automatic_tempdir_and_calls(
             "temp")
        fake_passthrough, passthrough_calls = fake_passthrough_and_calls
        package, package_recorder = make_fake_lambda_package_and_recorder(
            "zipfileobj")

        C.create(
            "fileobj", ["pip", "args"], fqpn,
            exclude_extension_modules=False,
            _automatic_tempdir=fake_automatic_tempdir,
            _passthrough=fake_passthrough,
            _LambdaPackage=package.recording__init__)

        assert package_recorder.to_zipfile_calls == [
            Call(args=("fileobj",), kwargs={})]
