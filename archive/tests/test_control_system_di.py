import lswitch_control as ctrl


class MockSystem:
    def run(self, *args, **kwargs):
        class R: returncode = 0; stdout = '1.5'
        return R()


def test_control_scale_injection():
    mock = MockSystem()
    ctrl.set_system(mock)
    res = ctrl.get_system_scale_factor()
    assert res == 1.5
    ctrl.set_system(None)