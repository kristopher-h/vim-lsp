# Copyright 2017 Kristopher Heijari
#
# This file is part of vim-liq.
#
# vim-liq.is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# vim-liq.is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with vim-liq.  If not, see <http://www.gnu.org/licenses/>.

"""This module tests installation and using the python language serverer "e2e"."""
import shutil
import tempfile

from context import *

import vimliq.install.python_lsp

# Hackky workaroudn to access MonkeyPatch class in module scoped fixture
# Suggestion taken from here: https://github.com/pytest-dev/pytest/issues/363
from _pytest.monkeypatch import MonkeyPatch

# Line is "one based" while col is "zero based" since vim seems to behave that way. E.g. call
# ":py import vim; vim.current.window.cursor = (4, 4)" jumps to line 4 col 5 (if counting 1 based)
FUNC_LINE = 4
FUNC_COL = 4
FUNC_CALL_LINE = 8
FUNC_CALL_COL = 13
VAR_LINE = 8
VAR_COL = 0
VAR_REF_LINE = 9
VAR_REF_COL = 6

install_dir = os.path.join(os.path.dirname(__file__), ".lsp_install_dir")
f_type = "python"
f_path = os.path.join(os.path.dirname(__file__), "python_test.py")
f_content = ""
with open(f_path) as f:
    f_content = f.read()

# Override static vim stuff
@pytest.fixture(scope="module")
def vim_static():
    mp = MonkeyPatch()
    mp.setattr("vimliq.vimutils.filetype", mock.Mock(return_value=f_type))
    mp.setattr("vimliq.vimutils.current_file", mock.Mock(return_value=f_path))
    mp.setattr("vimliq.vimutils.current_source", mock.Mock(return_value=f_content))


# This is the client manager used by all tests
@pytest.fixture(scope="module")
def LSP(request, vim_static):
    if not os.path.exists(install_dir):
        log.debug("Installing python lsp to %s", install_dir)
        os.makedirs(install_dir)
        langserver = vimliq.install.python_lsp.install(install_dir)
    else:
        # Just doing like this to avoid re-downloading everytime. If the dict returned from
        # the python lsp installation this needs to be updated.
        langserver = {'python': {'start_cmd': install_dir + '/python_lsp_server/bin/pyls',
                                 'log_arg': '--log-file', 'transport': 'STDIO'}}

    log.debug("langserver: %s", langserver)
    client_manager = vimliq.clientmanager.ClientManager(langserver)
    client_manager.add_client()

    # Start the newly added server and open our fake file
    client_manager.start_server()
    client_manager.td_did_open()

    def fin():
        # not using the convinience vim_mock since the scope is module
        sys.modules["vim"].eval.return_value = f_path
        client_manager.td_did_close()
        client_manager.shutdown_all()

    request.addfinalizer(fin)

    return client_manager


def test_did_save(LSP):
    LSP.td_did_save()


def test_did_change(LSP):
    LSP.td_did_change()


def test_definition(LSP, vim_mock):
    vim_mock.current.window.cursor = (FUNC_CALL_LINE, FUNC_CALL_COL)
    LSP.td_definition()
    vim_mock.command.assert_called_with("e {}".format(f_path))
    assert vim_mock.current.window.cursor == (FUNC_LINE, FUNC_COL)


def test_reference(LSP, vim_mock):
    vim_mock.current.window.cursor = (VAR_REF_LINE, VAR_REF_COL)
    LSP.td_references()
    print(vim_mock.eval.mock_calls)
    vim_mock.eval.assert_called_with(Partial('"filename":"{}"'.format(f_path)))
    vim_mock.eval.assert_called_with(Partial('"lnum":{}'.format(VAR_LINE)))
    vim_mock.eval.assert_called_with(Partial('"col":{}'.format(VAR_COL)))

def test_diagnostics(LSP):
    # For now just check the diagnostics list is updated
    LSP.process_diagnostics()
    print(LSP.diagnostics)
    assert LSP.diagnostics[f_path][0].start_line == 9
    assert LSP.diagnostics[f_path][0].message == "W391 blank line at end of file"


def test_symbols(LSP, vim_mock):
    LSP.td_symbols()
    print(vim_mock.eval.mock_calls)
    vim_mock.eval.assert_any_call(Partial('"text":"{}'.format("a_variable")))
    vim_mock.eval.assert_any_call(Partial('"text":"{}'.format("def a_function():")))


def test_completion(LSP, vim_mock, monkeypatch):
    # Mock omni_add_base directly to avoid problems with omnifunc call
    monkeypatch.setattr("vimliq.client.omni_add_base",
                        mock.Mock(return_value=("a_var", f_content)))
    vim_mock.current.window.cursor = (VAR_REF_LINE, VAR_REF_COL + 5)
    LSP.td_completion()
    print(vim_mock.command.mock_calls)
    # Check that a_variable is returned from the omnifunc function
    vim_mock.command.assert_called_with(Partial('"word":"a_variable"'))
