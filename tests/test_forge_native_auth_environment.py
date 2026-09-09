"""Exercise the actual Codex entrypoint branch in a filesystem fixture."""
from pathlib import Path
import json,os,shlex,subprocess

ROOT=Path(__file__).resolve().parents[1]


def configure(tmp_path, options=None, extra=None):
    source=(ROOT/'docker/ecosystem/workbench-entrypoint').read_text()
    start=source.index('  codex)\n')+len('  codex)\n')
    end=source.index('    ;;',start)
    branch=source[start:end].replace('native_home=/tmp/haloloom-codex-home',
                                   'native_home='+shlex.quote(str(tmp_path/'private')))
    home=tmp_path/'login';home.mkdir();(home/'auth.json').write_text('{}')
    env={'PATH':os.defpath,'HOME':str(tmp_path),'CODEX_HOME':str(home),
         'HALOLOOM_CODEX_BIN_HOST':'/bin/true'}
    if options is not None:env['FORGE_AGENT_OPTIONS_JSON']=json.dumps(options)
    env.update(extra or {})
    report="python3 -c 'import os,json; print(json.dumps({k:os.environ.get(k) for k in [\"FORGE_AGENT_OPTIONS_JSON\",\"FORGE_AGENT_FALLBACK_PROVIDER\",\"FORGE_AGENT_FALLBACK_MODEL\"]}))'"
    p=subprocess.run(['bash','-c','set -euo pipefail\n'+branch+'\n'+report],env=env,text=True,capture_output=True)
    assert p.returncode==0,p.stderr
    data=json.loads(p.stdout);data['options']=json.loads(data['FORGE_AGENT_OPTIONS_JSON'] or '{}')
    return data


def test_native_forge_inherits_private_native_login(tmp_path):
    data=configure(tmp_path)
    assert data['options']=={'auth_mode':'native_oauth','home':str(tmp_path/'private')}
    assert (tmp_path/'private/auth.json').stat().st_mode & 0o777 == 0o600
    assert data['FORGE_AGENT_FALLBACK_PROVIDER']=='none'
    assert data['FORGE_AGENT_FALLBACK_MODEL']=='off'


def test_native_forge_preserves_non_auth_options(tmp_path):
    data=configure(tmp_path,{'reasoning_effort':'high'})
    assert data['options']=={'reasoning_effort':'high','auth_mode':'native_oauth','home':str(tmp_path/'private')}


def test_explicit_forge_gateway_is_not_replaced(tmp_path):
    options={'auth_mode':'gateway','gateway':{'base_url':'https://invalid.example'}}
    assert configure(tmp_path,options)['options']==options


def test_gateway_override_without_mode_keeps_gateway_semantics(tmp_path):
    options={'gateway':{'base_url':'https://invalid.example'}}
    assert configure(tmp_path,options)['options']==options


def test_explicit_forge_native_home_is_preserved(tmp_path):
    options={'auth_mode':'native_oauth','home':'/operator/private-forge-home'}
    assert configure(tmp_path,options)['options']==options


def test_explicit_fallback_is_not_silently_changed(tmp_path):
    data=configure(tmp_path,extra={'FORGE_AGENT_FALLBACK_PROVIDER':'codex','FORGE_AGENT_FALLBACK_MODEL':'operator-model'})
    assert data['FORGE_AGENT_FALLBACK_PROVIDER']=='codex'
    assert data['FORGE_AGENT_FALLBACK_MODEL']=='operator-model'


def test_api_gateway_selection_retains_existing_branch(tmp_path):
    data=configure(tmp_path,extra={'OPENAI_API_KEY':'synthetic-do-not-send'})
    assert data['options']=={}
    assert data['FORGE_AGENT_FALLBACK_PROVIDER'] is None


def test_non_object_options_fail_closed(tmp_path):
    import pytest
    with pytest.raises(AssertionError,match='must be a JSON object'):
        configure(tmp_path,[])


def test_invalid_json_options_fail_closed(tmp_path):
    import pytest
    with pytest.raises(AssertionError,match='JSONDecodeError'):
        configure(tmp_path,extra={'FORGE_AGENT_OPTIONS_JSON':'{"invalid":'})
