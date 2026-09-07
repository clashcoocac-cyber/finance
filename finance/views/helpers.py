def preserve_filters(request, base_url):
    """Redirect back to base_url keeping the query string the page was
    showing when its form was submitted. POST handlers read `current_qs`
    (a hidden field carrying `request.GET.urlencode` from the filtered
    page) instead of `request.META['QUERY_STRING']`, because that reflects
    the POST target's own (empty) querystring, not the page the user saw.
    """
    qs = request.POST.get('current_qs', '')
    return f"{base_url}?{qs}" if qs else base_url
