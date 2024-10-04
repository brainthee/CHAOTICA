(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined' ? module.exports = factory() :
  typeof define === 'function' && define.amd ? define(factory) :
  (global = typeof globalThis !== 'undefined' ? globalThis : global || self, global.config = factory());
})(this, (function () { 'use strict';

  /* eslint-disable no-var */
  /* eslint-disable no-unused-vars */
  /* eslint-disable no-extra-boolean-cast */
  /* -------------------------------------------------------------------------- */
  /*                              Config                                        */
  /* -------------------------------------------------------------------------- */

  const configQueryMap = {
    'navbar-vertical-collapsed': 'phoenixIsNavbarVerticalCollapsed',
    'color-scheme': 'phoenixTheme',
    'navigation-type': 'phoenixNavbarPosition',
    'vertical-navbar-appearance': 'phoenixNavbarVerticalStyle',
    'horizontal-navbar-shape': 'phoenixNavbarTopShape',
    'horizontal-navbar-appearance': 'phoenixNavbarTopStyle'
  };

  const initialConfig = {
    phoenixIsNavbarVerticalCollapsed: false,
    phoenixTheme: '{% if request.user.is_authenticated %}{{ request.user.site_theme }}{% else %}auto{% endif %}',
    phoenixNavbarTopStyle: 'default',
    phoenixNavbarVerticalStyle: 'default',
    phoenixNavbarPosition: 'dual',
    phoenixNavbarTopShape: 'default',
    phoenixIsRTL: false,
    phoenixSupportChat: true
  };

  const CONFIG = { ...initialConfig };

  const setConfig = (payload, persist = true) => {
    Object.keys(payload).forEach(key => {
      CONFIG[key] = payload[key];
      if (persist) {
        localStorage.setItem(key, payload[key]);
      }
    });
  };

  const resetConfig = () => {
    Object.keys(initialConfig).forEach(key => {
      CONFIG[key] = initialConfig[key];
      localStorage.setItem(key, initialConfig[key]);
    });
  };

  const urlSearchParams = new URLSearchParams(window.location.search);
  const params = Object.fromEntries(urlSearchParams.entries());

  if (
    Object.keys(params).length > 0 &&
    Object.keys(params).includes('theme-control')
  ) {
    resetConfig();

    Object.keys(params).forEach(param => {
      if (configQueryMap[param]) {
        localStorage.setItem(configQueryMap[param], params[param]);
      }
    });
  }

  Object.keys(CONFIG).forEach(key => {
    if (localStorage.getItem(key) === null) {
      localStorage.setItem(key, CONFIG[key]);
    } else {
      try {
        setConfig({
          [key]: JSON.parse(localStorage.getItem(key))
        });
      } catch {
        setConfig({
          [key]: localStorage.getItem(key)
        });
      }
    }
  });

  if (!!JSON.parse(localStorage.getItem('phoenixIsNavbarVerticalCollapsed'))) {
    document.documentElement.classList.add('navbar-vertical-collapsed');
  }

  if (localStorage.getItem('phoenixTheme') === 'dark') {
    document.documentElement.setAttribute('data-bs-theme', 'dark');
  } else if (localStorage.getItem('phoenixTheme') === 'auto') {
    document.documentElement.setAttribute(
      'data-bs-theme',
      window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    );
  }

  {% comment %} if (localStorage.getItem('phoenixNavbarPosition') === 'horizontal') {
    document.documentElement.setAttribute('data-navigation-type', 'horizontal');
  }

  if (localStorage.getItem('phoenixNavbarPosition') === 'combo') {
    document.documentElement.setAttribute('data-navigation-type', 'combo');
  } {% endcomment %}

  var config = {
    config: CONFIG,
    reset: resetConfig,
    set: setConfig
  };

  return config;

}));
//# sourceMappingURL=config.js.map