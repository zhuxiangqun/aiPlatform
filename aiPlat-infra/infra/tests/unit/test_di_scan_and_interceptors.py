from infra.di import create_container, DIContainerConfig


def test_di_scan_packages_registers_injectables_and_interceptors_work():
    cfg = DIContainerConfig(
        scan_packages=["infra.tests.fixtures.di_scan_pkg"],
        interceptors=["timing"],
    )
    c = create_container(cfg)

    from infra.tests.fixtures.di_scan_pkg.services import GreeterService

    svc = c.resolve(GreeterService)
    assert svc.hello("world") == "hello world"

    timing = c.get_interceptor("timing")
    assert timing is not None
    assert timing.get_timing("hello") > 0.0

