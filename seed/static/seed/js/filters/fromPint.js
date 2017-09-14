angular.module('fromPint', []).filter('fromPint', function () {
  var pint_to_string = function (sig_figs, pint_obj) {
    var get_display_units = function (pint_format_string) {
      return {
        'foot ** 2': 'sq. ft',
        'kilobtu / foot ** 2 / year': 'kBtu/sq. ft./year'
      }[pint_format_string] || 'unknown_unit';
    };
    return pint_obj.magnitude.toFixed(sig_figs)
      + ' ' + get_display_units(pint_obj.units);
  };

  // TODO stick this into typedNumber somehow
  return function (maybePint) {
    var result = maybePint;
    if (_.isObject(maybePint)) {
      result = pint_to_string(1, maybePint);
    }
    return result;
  };
});
