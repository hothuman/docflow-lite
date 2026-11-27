"""One strict version/stage rule shared by UI and packaging."""
import re

_PATTERN=re.compile(r'(?P<base>[0-9]+\.[0-9]+\.[0-9]+)(?:(?P<stage>a|b|rc)(?P<number>[1-9][0-9]*))?\Z')


def stage(version):
    match=_PATTERN.fullmatch(version)
    if not match:raise ValueError('Unsupported release version: '+version)
    return {'a':'alpha','b':'beta','rc':'RC',None:'stable'}[match['stage']]


def is_prerelease(version):
    return stage(version)!='stable'


def local_state_namespace(version):
    """Never resume a project remembered by another stable major or preview."""
    if is_prerelease(version):
        return 'DocFlowLite-Preview'
    major = version.partition('.')[0]
    return 'DocFlowLite' if major in ('0', '1') else f'DocFlowLite-{major}'


def stage_label(version):
    return {
        'alpha': 'Альфа-версия',
        'beta': 'Бета-версия',
        'RC': 'Кандидат в релиз',
        'stable': 'Стабильный выпуск',
    }[stage(version)]
