class LoginError(Exception):
    pass


class InvalidWodBusterResponse(Exception):
    pass


class CloudflareBlocked(Exception):
    pass


class BookingFailed(Exception):
    pass


class ClassIsFull(Exception):
    pass


class ClassNotFound(Exception):
    pass


class NoPrivateClassesAvailable(Exception):
    pass
