"""Product field checks, not a legal conclusion or invented company data."""
def assess(snapshot,kind,custom_template=''):
    from .document_fields import readiness_context,configured_values
    organization=snapshot['profile'];quote=None;required_missing=[]
    if kind.startswith('estimate_'):
        quote=next((q for q in snapshot['estimates'] if q['kind']==kind.removeprefix('estimate_')),None)
        if quote:organization=quote['payload']['profile']
    if organization.get('template_required_fields',{}).get(kind):
        organization,quote,values=readiness_context(snapshot,kind)
        _,required_missing=configured_values(values,organization,kind)
    labels={'organization_name':'название исполнителя','contact':'контакты','details':'реквизиты'}
    missing=[label for key,label in labels.items() if not organization.get(key,'').strip()]
    template=custom_template or organization.get('template_paths',{}).get(kind,'')
    return {'profile':organization,'missing':missing,'required_missing':required_missing,'neutral':bool(missing),'blocked':bool(template and (missing or required_missing)),'quote_snapshot':quote is not None,'template_selected':bool(template)}
