"""Product field checks, not a legal conclusion or invented company data."""
def assess(snapshot,kind,custom_template=''):
    organization=snapshot['profile'];quote=None
    if kind.startswith('estimate_'):
        expected=kind.removeprefix('estimate_');matches=[q for q in snapshot['estimates'] if q['kind']==expected]
        if matches:quote=matches[0];organization=quote['payload']['profile']
    labels={'organization_name':'название исполнителя','contact':'контакты','details':'реквизиты'}
    missing=[label for key,label in labels.items() if not organization.get(key,'').strip()]
    template=custom_template or organization.get('template_paths',{}).get(kind,'')
    return {'profile':organization,'missing':missing,'neutral':bool(missing),'blocked':bool(template and missing),'quote_snapshot':quote is not None,'template_selected':bool(template)}
