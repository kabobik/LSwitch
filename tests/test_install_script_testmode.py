import os
import tempfile
import shutil
import subprocess


def test_install_script_test_mode(tmp_path):
    prefix = str(tmp_path / 'lswitch_test_prefix')
    os.environ['LSWITCH_TEST_PREFIX'] = prefix

    # Run install script
    res = subprocess.run(['bash', 'install.sh'], cwd=os.getcwd(), capture_output=True, text=True)
    out = res.stdout + res.stderr
    # Ensure script completed successfully
    assert res.returncode == 0

    # Check log marker
    log = os.path.join(prefix, '.lswitch_install_log')
    assert os.path.exists(log)
    with open(log, 'r') as f:
        data = f.read()
    assert 'TEST_MODE=1' in data

    # Check some installed files exist under prefix
    assert os.path.exists(os.path.join(prefix, 'usr', 'local', 'bin', 'lswitch'))
    # GUI tray removed — control binary and desktop file should NOT be installed
    assert not os.path.exists(os.path.join(prefix, 'usr', 'local', 'bin', 'lswitch-control'))
    assert os.path.exists(os.path.join(prefix, 'usr', 'local', 'lib', 'lswitch', 'adapters'))
    assert not os.path.exists(os.path.join(prefix, 'usr', 'share', 'applications', 'lswitch-control.desktop'))

    # Cleanup
    del os.environ['LSWITCH_TEST_PREFIX']
    shutil.rmtree(prefix)