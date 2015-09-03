from django.test import TestCase
from seed.tasks import _normalize_address_str


def make_test(message, expected):
    def run(self):
        result = _normalize_address_str(message)
        self.assertEquals(expected, result)
    return run


# Metaclass to create individual test methods per test case.
class NormalizeAddressTester(type):
    def __new__(cls, name, bases, attrs):
        cases = attrs.get('cases', [])

        for doc, message, expected in cases:
            test = make_test(message, expected)
            test_name = 'test_normalize_address_%s' % doc.lower().replace(' ', '_')
            test.__doc__ = doc
            test.__name__ = test_name
            attrs[test_name] = test
        return super(NormalizeAddressTester, cls).__new__(cls, name, bases, attrs)


class NormalizeStreetAddressTests(TestCase):
    __metaclass__ = NormalizeAddressTester

    # test name, input, expected output
    cases = [
        ('simple', '123 Test St.', '123 test st'),
        ('none input', None, None),
        ('empty input', '', None),
        ('missing number', 'Test St.', 'test st'),
        ('missing street', '123', '123'),
        ('integer address', 123, '123'),
        ('strip leading zeros', '0000123', '123'),
        ('street 1', 'STREET', 'st'),
        ('street 2', 'Street', 'st'),
        ('boulevard', 'Boulevard', 'blvd'),
        ('avenue', 'avenue', 'ave'),
        ('trailing direction', '123 Test St. NE', '123 test st ne'),
        ('prefix direction', '123 South Test St.', '123 south test st'),
        ('verbose direction', '123 Test St. Northeast', '123 test st northeast'),
    ]
