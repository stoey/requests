#-*- coding: utf-8 -*-

"""
requests.monkeys
~~~~~~~~~~~~~~~~

Urllib2 Monkey patches.

"""
import urllib2
import re

import sys
if sys.version_info[:3] < (2,5,4):
    import httplib
    def build_opener(*handlers):
        """Create an opener object from a list of handlers.

        The opener will use several default handlers, including support
        for HTTP, FTP and when applicable, HTTPS.

        If any of the handlers passed as arguments are subclasses of the
        default handlers, the default handlers will not be used.
        """
        import types
        def isclass(obj):
            return isinstance(obj, types.ClassType) or hasattr(obj, "__bases__")

        opener = urllib2.OpenerDirector()
        default_classes = [urllib2.ProxyHandler, urllib2.UnknownHandler, urllib2.HTTPHandler,
                           urllib2.HTTPDefaultErrorHandler, urllib2.HTTPRedirectHandler,
                           urllib2.FTPHandler, urllib2.FileHandler, urllib2.HTTPErrorProcessor]
        if hasattr(httplib, 'HTTPS'):
            default_classes.append(urllib2.HTTPSHandler)
        skip = set()
        for klass in default_classes:
            for check in handlers:
                if isclass(check):
                    if issubclass(check, klass):
                        skip.add(klass)
                elif isinstance(check, klass):
                    skip.add(klass)
        for klass in skip:
            default_classes.remove(klass)

        for klass in default_classes:
            opener.add_handler(klass())

        for h in handlers:
            if isclass(h):
                h = h()
            opener.add_handler(h)
        return opener


class Request(urllib2.Request):
    """Hidden wrapper around the urllib2.Request object. Allows for manual
    setting of HTTP methods.
    """

    def __init__(self, url, data=None, headers={}, origin_req_host=None, unverifiable=False, method=None):
        urllib2.Request.__init__(self, url, data, headers, origin_req_host, unverifiable)
        self.method = method

    def get_method(self):
        if self.method:
            return self.method

        return urllib2.Request.get_method(self)


class HTTPRedirectHandler(urllib2.HTTPRedirectHandler):
    """HTTP Redirect handler."""
    def http_error_301(self, req, fp, code, msg, headers):
        pass

    http_error_302 = http_error_303 = http_error_307 = http_error_301



class HTTPBasicAuthHandler(urllib2.HTTPBasicAuthHandler):
    """HTTP Basic Auth Handler with authentication loop fixes."""

    def __init__(self, *args, **kwargs):
        urllib2.HTTPBasicAuthHandler.__init__(self, *args, **kwargs)
        self.retried_req = None
        self.retried = 0


    def reset_retry_count(self):
        # Python 2.6.5 will call this on 401 or 407 errors and thus loop
        # forever. We disable reset_retry_count completely and reset in
        # http_error_auth_reqed instead.
        pass


    def http_error_auth_reqed(self, auth_header, host, req, headers):
        # Reset the retry counter once for each request.
        if req is not self.retried_req:
            self.retried_req = req
            self.retried = 0

        return urllib2.HTTPBasicAuthHandler.http_error_auth_reqed(
            self, auth_header, host, req, headers
        )



class HTTPForcedBasicAuthHandler(HTTPBasicAuthHandler):
    """HTTP Basic Auth Handler with forced Authentication."""

    auth_header = 'Authorization'
    rx = re.compile('(?:.*,)*[ \t]*([^ \t]+)[ \t]+'
                    'realm=(["\'])(.*?)\\2', re.I)

    def __init__(self,  *args, **kwargs):
        HTTPBasicAuthHandler.__init__(self, *args, **kwargs)


    def http_error_401(self, req, fp, code, msg, headers):
        url = req.get_full_url()
        response = self._http_error_auth_reqed('www-authenticate', url, req, headers)
        self.reset_retry_count()
        return response

    http_error_404 = http_error_401


    def _http_error_auth_reqed(self, authreq, host, req, headers):

        authreq = headers.get(authreq, None)

        if self.retried > 5:
            # retry sending the username:password 5 times before failing.
            raise urllib2.HTTPError(req.get_full_url(), 401, "basic auth failed",
                            headers, None)
        else:
            self.retried += 1

        if authreq:

            mo = self.rx.search(authreq)

            if mo:
                scheme, quote, realm = mo.groups()

                if scheme.lower() == 'basic':
                    response = self.retry_http_basic_auth(host, req, realm)

                    if response and response.code not in (401, 404):
                        self.retried = 0
                    return response
        else:
            response = self.retry_http_basic_auth(host, req, 'Realm')

            if response and response.code not in (401, 404):
                self.retried = 0
            return response



class HTTPDigestAuthHandler(urllib2.HTTPDigestAuthHandler):

    def __init__(self, *args, **kwargs):
        urllib2.HTTPDigestAuthHandler.__init__(self, *args, **kwargs)
        self.retried_req = None

    def reset_retry_count(self):
        # Python 2.6.5 will call this on 401 or 407 errors and thus loop
        # forever. We disable reset_retry_count completely and reset in
        # http_error_auth_reqed instead.
        pass

    def http_error_auth_reqed(self, auth_header, host, req, headers):
        # Reset the retry counter once for each request.
        if req is not self.retried_req:
            self.retried_req = req
            self.retried = 0
        # In python < 2.5 AbstractDigestAuthHandler raises a ValueError if
        # it doesn't know about the auth type requested. This can happen if
        # somebody is using BasicAuth and types a bad password.

        try:
            return urllib2.HTTPDigestAuthHandler.http_error_auth_reqed(
                        self, auth_header, host, req, headers)
        except ValueError, inst:
            arg = inst.args[0]
            if arg.startswith("AbstractDigestAuthHandler doesn't know "):
                return
            raise
