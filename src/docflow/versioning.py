"""One strict version/stage rule shared by UI and packaging."""
import re

_PATTERN=re.compile(r'(?P<base>[0-9]+\.[0-9]+\.[0-9]+)(?:(?P<stage>a|b|rc)(?P<number>[1-9][0-9]*))?\Z')


def stage(version):
    match=_PATTERN.fullmatch(version)
    if not match:raise ValueError('Unsupported release version: '+version)
    return {'a':'alpha','b':'beta','rc':'RC',None:'stable'}[match['stage']]


def is_prerelease(version):
    return stage(version)!='stable'
