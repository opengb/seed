/*
 * :copyright (c) 2014 - 2017, The Regents of the University of California, through Lawrence Berkeley National Laboratory (subject to receipt of any required approvals from the U.S. Department of Energy) and contributors. All rights reserved.
 * :author
 */
angular.module('BE.seed.controller.localization', [])
  .controller('localization_controller', [
    '$scope',
    '$translate',
    'urls',
    'auth_payload',
    'user_profile_payload',
    'user_service',
    function ($scope,
              $translate,
              urls,
              auth_payload,
              user_profile_payload,
              user_service) {
      $scope.auth = auth_payload.auth;
      $scope.user = user_profile_payload;
      $scope.user_updated = false;
      var user_copy = angular.copy($scope.user);
      $scope.username = user_profile_payload.first_name + ' ' + user_profile_payload.last_name;

      /**
       * updates the user's localization prefs
       */
      $scope.submit_form = function () {
        user_service
          .update_localization_prefs($scope.user)
          .then(function (result) {
            $scope.user_updated = true;
            $translate.use($scope.user.language_preference);
            user_copy = angular.copy($scope.user);
          });
      };

      /**
       * resets the form
       */
      $scope.reset_form = function () {
        $scope.user = angular.copy(user_copy);
      };

    }]);

