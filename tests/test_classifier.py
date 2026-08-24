import pytest

from ipmi_mcp.classifier import Kind, classify

READ_COMMANDS = [
    "chassis power status",
    "power status",
    "chassis status",
    "sdr",
    "sdr list",
    "sdr elist full",
    "sensor list",
    "sensor get 'CPU Temp'",
    "sel list",
    "sel elist",
    "sel info",
    "mc info",
    "bmc info",
    "fru print",
    "lan print 1",
    "user list 1",
    "channel getaccess 1",
    "sol info",
]

MUTATING_COMMANDS = [
    "chassis bootdev pxe",
    "sel clear",                       # NOT a read despite starting with "sel"
    "sensor thresh 'CPU Temp' lower 0 0 0",
    "user set password 2 secret",
    "lan set 1 ipaddr 192.168.1.50",
    "raw 0x00 0x01",
    "sol activate",                    # interactive session, treated as mutating
    "mc setenables",
    "",                                # empty
    "totally unknown command",
    "chassis power status; sel clear",  # chaining -> mutating
]

HOST_CRITICAL_COMMANDS = [
    "power off",
    "power cycle",
    "power reset",
    "power soft",
    "chassis power off",
    "chassis power cycle",
    "chassis power reset",
    "mc reset cold",
    "bmc reset warm",
]


@pytest.mark.parametrize("command", READ_COMMANDS)
def test_read_commands_are_read(command):
    assert classify(command).kind is Kind.READ


@pytest.mark.parametrize("command", MUTATING_COMMANDS)
def test_mutating_commands_are_mutating(command):
    assert classify(command).kind is Kind.MUTATING


@pytest.mark.parametrize("command", HOST_CRITICAL_COMMANDS)
def test_host_critical_flag(command):
    verdict = classify(command)
    assert verdict.kind is Kind.MUTATING
    assert verdict.host_critical is True


def test_power_on_is_mutating_but_not_host_critical():
    # Powering ON is mutating (needs confirm) but not host-critical (no force).
    verdict = classify("chassis power on")
    assert verdict.kind is Kind.MUTATING
    assert verdict.host_critical is False


def test_shell_meta_beats_read_allowlist():
    assert classify("sensor list; sel clear").kind is Kind.MUTATING
