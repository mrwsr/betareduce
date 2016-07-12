from .. import _cli as C
import contextlib
import logging
import pytest


class TestRun(object):
    """
    Tests for :py:func:`betareduce._cli.run`
    """

    @pytest.fixture
    def make_fake_open_and_calls(self):
        """
        Returns a maker for a fake :py:func:`open` and a calls list
        for it.
        """
        calls = []

        def make_fake_open(yields):
            @contextlib.contextmanager
            def fake_open(path, mode):
                calls.append((path, mode))
                yield yields
            return fake_open, calls

        return make_fake_open

    @pytest.fixture
    def fake_create_and_calls(self):
        """
        Returns a fake for :py:func:`betareduce._core.create` and a
        calls list for it.
        """
        calls = []

        def fake_create(fileobj, requirements, root,
                        exclude_extension_modules):
            calls.append((fileobj, requirements, root,
                          exclude_extension_modules))
        return fake_create, calls

    @pytest.mark.parametrize("outfile,requirements", [
        ("outfile", ["requirement1"]),
        ("outfile", ["requirement1", "requirement2"]),
    ])
    def test_outfile_and_requirements(self,
                                      make_fake_open_and_calls,
                                      fake_create_and_calls,
                                      outfile, requirements):
        """
        :py:func:`betareduce._core.run` extracts the desired outfile
        and requirements from the command line.
        """
        fake_open, open_calls = make_fake_open_and_calls("file")
        fake_create, create_calls = fake_create_and_calls

        C.run(_argv=[outfile] + requirements,
              _open=fake_open,
              _create=fake_create)

        assert open_calls == [(outfile, 'wb')]
        assert create_calls == [("file", requirements, None, True)]

    @pytest.mark.parametrize("staging_flag", [
        "--staging-directory", "-d",
    ])
    def test_staging_directory(self,
                               make_fake_open_and_calls,
                               fake_create_and_calls,
                               staging_flag):
        """
        :py:func:`betareduce._core.run` extracts the desired staging
        directory from the command line.
        """
        fake_open, open_calls = make_fake_open_and_calls("file")
        fake_create, create_calls = fake_create_and_calls

        C.run(_argv=["outfile", "requirement", staging_flag, "staging"],
              _open=fake_open,
              _create=fake_create)

        assert create_calls == [("file", ["requirement"], "staging", True)]

    @pytest.mark.parametrize("allow_extensions_flag", [
        [], ["--allow-extension"], ["-a"],
    ])
    def test_allow_extensions(self,
                              make_fake_open_and_calls,
                              fake_create_and_calls,
                              allow_extensions_flag):
        """
        :py:func:`betareduce._core.run` allows extensions if
        configured to via the command line.
        """
        fake_open, open_calls = make_fake_open_and_calls("file")
        fake_create, create_calls = fake_create_and_calls

        C.run(_argv=["outfile", "requirement"] + allow_extensions_flag,
              _open=fake_open,
              _create=fake_create)

        extension_allowed = not allow_extensions_flag
        assert create_calls == [
            ("file", ["requirement"], None, extension_allowed),
        ]

    @pytest.mark.parametrize("quiet_flag", [
        [], ["--quiet"], ["-q"],
    ])
    def test_quiet(self,
                   make_fake_open_and_calls,
                   fake_create_and_calls,
                   quiet_flag,
                   monkeypatch):
        """
        :py:func:`betareduce._core.run` settings the log level to
        ERROR when the quiet command line argument is present.
        """
        fake_open, open_calls = make_fake_open_and_calls("file")
        fake_create, create_calls = fake_create_and_calls

        monkeypatch.setattr(logging, "root",
                            logging.RootLogger(logging.WARNING))

        C.run(_argv=["outfile", "requirement"] + quiet_flag,
              _open=fake_open,
              _create=fake_create)

        if quiet_flag:
            assert logging.root.level == logging.ERROR
        else:
            assert logging.root.level == logging.DEBUG
