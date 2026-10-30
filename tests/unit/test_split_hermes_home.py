from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from hermes_feishu_card import hook_runtime
from hermes_feishu_card.integrity import sanitize_integrity_snapshot
from hermes_feishu_card.runtime_ownership import runtime_target_identity


def test_target_identity_binds_home_without_changing_legacy_identity(tmp_path):
    root = tmp_path / 'src'
    a, b = tmp_path / 'profile-a', tmp_path / 'profile-b'
    assert runtime_target_identity(root, home=tmp_path) == runtime_target_identity(root)
    assert runtime_target_identity(root, home=a) != runtime_target_identity(root, home=b)
    assert runtime_target_identity(root, home=a) != runtime_target_identity(root)


def test_gateway_process_home_can_be_separate_but_must_exist(tmp_path, monkeypatch):
    source = tmp_path / 'src/gateway/run.py'
    source.parent.mkdir(parents=True)
    source.touch()
    home = tmp_path / 'data'
    home.mkdir()
    (home / 'config.yaml').write_text('{}')
    monkeypatch.setitem(sys.modules, 'gateway.run', SimpleNamespace(__file__=str(source)))
    monkeypatch.setattr(hook_runtime.importlib, 'import_module', lambda _: SimpleNamespace(get_process_hermes_home=lambda: home))
    assert hook_runtime.gateway_drain_home_verified()
    home.rename(tmp_path / 'moved')
    assert not hook_runtime.gateway_drain_home_verified()


@pytest.mark.parametrize('reason', ['runtime_owner_unverified', 'runtime_owner_conflict', 'runtime_owner_capacity_exceeded'])
def test_integrity_preserves_safe_owner_diagnostic(reason):
    assert sanitize_integrity_snapshot({'last_reason': reason})['last_reason'] == reason


def test_config_binding_ignores_ambient_home_and_rejects_mismatch(tmp_path, monkeypatch):
    from hermes_feishu_card.instance_binding import configured_hermes_home, setup_hermes_home
    root = tmp_path / 'src'
    home = tmp_path / 'data'; home.mkdir(); (home/'config.yaml').write_text('{}')
    other = tmp_path/'other'; other.mkdir(); (other/'config.yaml').write_text('{}')
    monkeypatch.setenv('HERMES_HOME', str(other))
    assert configured_hermes_home(root, {}) == root.parent
    cfg = {'service': {'hermes_home': str(home)}}
    assert setup_hermes_home(root, cfg, home) == home
    with pytest.raises(ValueError, match='conflicts'):
        setup_hermes_home(root, cfg, other)
    for bad in ['', '.', 12]:
        with pytest.raises(ValueError):
            configured_hermes_home(root, {'service': {'hermes_home': bad}})


def test_legacy_task_home_api_cannot_authorize_split_home(tmp_path, monkeypatch):
    source=tmp_path/'src/gateway/run.py'; source.parent.mkdir(parents=True); source.touch()
    home=tmp_path/'data'; home.mkdir(); (home/'config.yaml').write_text('{}')
    monkeypatch.setitem(sys.modules,'gateway.run',SimpleNamespace(__file__=str(source)))
    monkeypatch.setattr(hook_runtime.importlib,'import_module',lambda _:SimpleNamespace(get_hermes_home=lambda:home))
    assert not hook_runtime.gateway_drain_home_verified()


def test_config_binding_preserves_legacy_bootstrap_but_requires_split_config(tmp_path):
    from hermes_feishu_card.instance_binding import configured_hermes_home
    root = tmp_path / 'hermes'
    assert configured_hermes_home(root, {'service': {'hermes_home': str(tmp_path)}}) == tmp_path
    split = tmp_path / 'data'
    split.mkdir()
    with pytest.raises(ValueError, match='config.yaml'):
        configured_hermes_home(root, {'service': {'hermes_home': str(split)}})


def test_bound_maintenance_commands_use_only_selected_home_and_pm(tmp_path, monkeypatch):
    import os
    from hermes_feishu_card import maintenance_update as m
    root=tmp_path/'source'; (root/'pm').mkdir(parents=True)
    (root/'pm/__init__.py').touch()
    (root/'pm/environments.py').write_text('import os\nfrom pathlib import Path\ndef committed_venv(root): return Path(os.environ["HERMES_HOME"])/"runtime"\n')
    home=tmp_path/'profile-a'; home.mkdir(); (home/'config.yaml').write_text('{}')
    runtime=home/'runtime'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    runtime.parent.mkdir(parents=True); runtime.write_text('fixture')
    monkeypatch.setenv('HERMES_HOME',str(tmp_path/'profile-b'))
    binding=m.resolve_hermes_command_binding(root,hermes_home=home)
    assert binding.runtime_python==runtime and binding.home==home
    calls=[]
    def run(argv,timeout,**kwargs):
        calls.append((argv,kwargs));return m.CommandResult(tuple(argv),0,'','')
    assert m.set_gateway_external_drain(root,active=True,hermes_home=home,run=run)
    for command in [('gateway','stop'),('gateway','start'),('update','--check')]:
        m.run_hermes_command(binding,command,5,run=run,base_environment={'HERMES_HOME':'wrong','HERMES_PROFILE':'wrong'})
    assert all(c[1]['env']['HERMES_HOME']==str(home) and c[1]['cwd']==root for c in calls)
    assert all('HERMES_PROFILE' not in c[1]['env'] for c in calls)
    runtime.unlink()
    with pytest.raises(m.MaintenanceRefused,match='PM runtime'):
        m.resolve_hermes_command_binding(root,hermes_home=home)


def test_split_home_update_is_refused_before_external_commands(tmp_path):
    from hermes_feishu_card import maintenance_update as m
    artifact=SimpleNamespace(version='test',sha256='a'*64)
    result=m.inspect_update(hermes_root=tmp_path/'source',hermes_home=tmp_path/'data',artifact=artifact,installed_hfc_version='test',active_sessions=0,run=lambda *a,**k:pytest.fail('must not execute'))
    assert not result.ready and result.reason_code=='split_home_requires_manual_update'


def test_setup_home_env_survives_reload_and_does_not_replace_other_values(tmp_path):
    from hermes_feishu_card.config import load_config
    from hermes_feishu_card.install.envfile import update_hfc_env
    cfg=tmp_path/'sidecar.yaml'; cfg.write_text('{}')
    env=tmp_path/'selected.env'; env.write_text('OTHER=keep\n')
    home=tmp_path/'profile a'; home.mkdir(); (home/'config.yaml').write_text('{}')
    update_hfc_env(env,{'HERMES_FEISHU_CARD_HERMES_HOME':str(home)})
    assert load_config(cfg,env_file=env)['service']['hermes_home']==str(home)
    assert 'OTHER=keep' in env.read_text()


def test_shared_source_default_home_update_is_also_refused(tmp_path):
    from hermes_feishu_card import maintenance_update as m
    result=m.inspect_update(hermes_root=tmp_path/'source',hermes_home=tmp_path,shared_source=True,
        artifact=SimpleNamespace(version='test',sha256='a'*64),installed_hfc_version='test',active_sessions=0,
        run=lambda *a,**k:pytest.fail('shared source must not execute updater'))
    assert result.reason_code=='shared_source_requires_manual_update' and not result.ready
