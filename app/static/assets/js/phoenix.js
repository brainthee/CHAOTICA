(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined' ? module.exports = factory(require('bootstrap')) :
  typeof define === 'function' && define.amd ? define(['bootstrap'], factory) :
  (global = typeof globalThis !== 'undefined' ? globalThis : global || self, global.phoenix = factory(global.bootstrap));
})(this, (function (bootstrap) { 'use strict';

  /* -------------------------------------------------------------------------- */
  /*                                    Utils                                   */
  /* -------------------------------------------------------------------------- */
  const docReady = fn => {
    // see if DOM is already available
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      setTimeout(fn, 1);
    }
  };

  const toggleColor = (lightColor, darkColor) => {
    const currentMode = getItemFromStore('phoenixTheme');
    const mode = currentMode === 'auto' ? getSystemTheme() : currentMode;
    return mode === 'light' ? lightColor : darkColor;
  };

  const resize = fn => window.addEventListener('resize', fn);

  const isIterableArray = array => Array.isArray(array) && !!array.length;

  const camelize = str => {
    const text = str.replace(/[-_\s.]+(.)?/g, (_, c) =>
      c ? c.toUpperCase() : ''
    );
    return `${text.substr(0, 1).toLowerCase()}${text.substr(1)}`;
  };

  const getData = (el, data) => {
    try {
      return JSON.parse(el.dataset[camelize(data)]);
    } catch (e) {
      return el.dataset[camelize(data)];
    }
  };

  /* ----------------------------- Colors function ---------------------------- */

  const hexToRgb = hexValue => {
    let hex;
    hexValue.indexOf('#') === 0
      ? (hex = hexValue.substring(1))
      : (hex = hexValue);
    // Expand shorthand form (e.g. "03F") to full form (e.g. "0033FF")
    const shorthandRegex = /^#?([a-f\d])([a-f\d])([a-f\d])$/i;
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(
      hex.replace(shorthandRegex, (m, r, g, b) => r + r + g + g + b + b)
    );
    return result
      ? [
          parseInt(result[1], 16),
          parseInt(result[2], 16),
          parseInt(result[3], 16)
        ]
      : null;
  };

  const rgbaColor = (color = '#fff', alpha = 0.5) =>
    `rgba(${hexToRgb(color)}, ${alpha})`;

  /* --------------------------------- Colors --------------------------------- */

  const getColor = (name, dom = document.documentElement) => {
    return getComputedStyle(dom).getPropertyValue(`--phoenix-${name}`).trim();
  };

  const hasClass = (el, className) => {
    return el.classList.value.includes(className);
  };

  const addClass = (el, className) => {
    el.classList.add(className);
  };

  const getOffset = el => {
    const rect = el.getBoundingClientRect();
    const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    return { top: rect.top + scrollTop, left: rect.left + scrollLeft };
  };

  const isScrolledIntoView = el => {
    let top = el.offsetTop;
    let left = el.offsetLeft;
    const width = el.offsetWidth;
    const height = el.offsetHeight;

    while (el.offsetParent) {
      // eslint-disable-next-line no-param-reassign
      el = el.offsetParent;
      top += el.offsetTop;
      left += el.offsetLeft;
    }

    return {
      all:
        top >= window.pageYOffset &&
        left >= window.pageXOffset &&
        top + height <= window.pageYOffset + window.innerHeight &&
        left + width <= window.pageXOffset + window.innerWidth,
      partial:
        top < window.pageYOffset + window.innerHeight &&
        left < window.pageXOffset + window.innerWidth &&
        top + height > window.pageYOffset &&
        left + width > window.pageXOffset
    };
  };

  const breakpoints = {
    xs: 0,
    sm: 576,
    md: 768,
    lg: 992,
    xl: 1200,
    xxl: 1540
  };

  const getBreakpoint = el => {
    const classes = el && el.classList.value;
    let breakpoint;
    if (classes) {
      breakpoint =
        breakpoints[
          classes
            .split(' ')
            .filter(cls => cls.includes('navbar-expand-'))
            .pop()
            .split('-')
            .pop()
        ];
    }
    return breakpoint;
  };

  /* --------------------------------- Cookie --------------------------------- */

  const setCookie = (name, value, seconds) => {
    const expires = window.dayjs().add(seconds, 'second').toDate();
    document.cookie = `${name}=${value};expires=${expires}`;
  };

  const getCookie = name => {
    const keyValue = document.cookie.match(`(^|;) ?${name}=([^;]*)(;|$)`);
    return keyValue ? keyValue[2] : keyValue;
  };

  const settings = {
    tinymce: {
      theme: 'oxide'
    },
    chart: {
      borderColor: 'rgba(255, 255, 255, 0.8)'
    }
  };

  /* -------------------------- Chart Initialization -------------------------- */

  const newChart = (chart, config) => {
    const ctx = chart.getContext('2d');
    return new window.Chart(ctx, config);
  };

  /* ---------------------------------- Store --------------------------------- */

  const getItemFromStore = (key, defaultValue, store = localStorage) => {
    try {
      return JSON.parse(store.getItem(key)) || defaultValue;
    } catch {
      return store.getItem(key) || defaultValue;
    }
  };

  const setItemToStore = (key, payload, store = localStorage) =>
    store.setItem(key, payload);
  const getStoreSpace = (store = localStorage) =>
    parseFloat(
      (
        escape(encodeURIComponent(JSON.stringify(store))).length /
        (1024 * 1024)
      ).toFixed(2)
    );

  /* get Dates between */

  const getDates = (
    startDate,
    endDate,
    interval = 1000 * 60 * 60 * 24
  ) => {
    const duration = endDate - startDate;
    const steps = duration / interval;
    return Array.from(
      { length: steps + 1 },
      (v, i) => new Date(startDate.valueOf() + interval * i)
    );
  };

  const getPastDates = duration => {
    let days;

    switch (duration) {
      case 'week':
        days = 7;
        break;
      case 'month':
        days = 30;
        break;
      case 'year':
        days = 365;
        break;

      default:
        days = duration;
    }

    const date = new Date();
    const endDate = date;
    const startDate = new Date(new Date().setDate(date.getDate() - (days - 1)));
    return getDates(startDate, endDate);
  };

  /* Get Random Number */
  const getRandomNumber = (min, max) => {
    return Math.floor(Math.random() * (max - min) + min);
  };

  const getSystemTheme = () =>
    window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';

  // export const handleThemeDropdownIcon = value => {
  //   document.querySelectorAll('[data-theme-dropdown-toggle-icon]').forEach(el => {
  //     const theme = getData(el, 'theme-dropdown-toggle-icon');

  //     if (value === theme) {
  //       el.classList.remove('d-none');
  //     } else {
  //       el.classList.add('d-none');
  //     }
  //   });
  // };
  // handleThemeDropdownIcon(getItemFromStore('phoenixTheme'));

  var utils = {
    docReady,
    toggleColor,
    resize,
    isIterableArray,
    camelize,
    getData,
    hasClass,
    addClass,
    hexToRgb,
    rgbaColor,
    getColor,
    breakpoints,
    // getGrays,
    getOffset,
    isScrolledIntoView,
    getBreakpoint,
    setCookie,
    getCookie,
    newChart,
    settings,
    getItemFromStore,
    setItemToStore,
    getStoreSpace,
    getDates,
    getPastDates,
    getRandomNumber,
    getSystemTheme
    // handleThemeDropdownIcon
  };

  const docComponentInit = () => {
    const componentCards = document.querySelectorAll('[data-component-card]');
    const iconCopiedToast = document.getElementById('icon-copied-toast');
    const iconCopiedToastInstance = new bootstrap.Toast(iconCopiedToast);

    componentCards.forEach(card => {
      const copyCodeBtn = card.querySelector('.copy-code-btn');
      const copyCodeEl = card.querySelector('.code-to-copy');
      const previewBtn = card.querySelector('.preview-btn');
      const collapseElement = card.querySelector('.code-collapse');
      const collapseInstance = bootstrap.Collapse.getOrCreateInstance(collapseElement, {
        toggle: false
      });

      previewBtn?.addEventListener('click', () => {
        collapseInstance.toggle();
      });

      copyCodeBtn?.addEventListener('click', () => {
        const el = document.createElement('textarea');
        el.value = copyCodeEl.innerHTML;
        document.body.appendChild(el);

        el.select();
        document.execCommand('copy');
        document.body.removeChild(el);

        iconCopiedToast.querySelector(
          '.toast-body'
        ).innerHTML = `<code class='text-body-quaternary'>Code has been copied to clipboard.</code>`;
        iconCopiedToastInstance.show();
      });
    });
  };

  /* eslint-disable */
  const orders = [
    {
      id: 1,
      dropdownId: 'order-dropdown-1',
      orderId: '#2181',
      mailLink: 'mailto:carry@example.com',
      customer: 'Carry Anna',
      date: '10/03/2023',
      address: 'Carry Anna, 2392 Main Avenue, Penasauka, New Jersey 02149',
      deliveryType: 'Cash on Delivery',
      status: 'Completed',
      badge: { type: 'success', icon: 'fas fa-check' },
      amount: '$99'
    },
    {
      id: 2,
      dropdownId: 'order-dropdown-2',
      orderId: '#2182',
      mailLink: 'mailto:milind@example.com',
      customer: 'Milind Mikuja',
      date: '10/03/2023',
      address: 'Milind Mikuja, 1 Hollywood Blvd,Beverly Hills, California 90210',
      deliveryType: 'Cash on Delivery',
      status: 'Processing',
      badge: { type: 'primary', icon: 'fas fa-redo' },
      amount: '$120'
    },
    {
      id: 3,
      dropdownId: 'order-dropdown-3',
      orderId: '#2183',
      mailLink: 'mailto:stanly@example.com',
      customer: 'Stanly Drinkwater',
      date: '30/04/2023',
      address: 'Stanly Drinkwater, 1 Infinite Loop, Cupertino, California 90210',
      deliveryType: 'Local Delivery',
      status: 'On Hold',
      badge: { type: 'secondary', icon: 'fas fa-ban' },
      amount: '$70'
    },
    {
      id: 4,
      dropdownId: 'order-dropdown-4',
      orderId: '#2184',
      mailLink: 'mailto:bucky@example.com',
      customer: 'Bucky Robert',
      date: '30/04/2023',
      address: 'Bucky Robert, 1 Infinite Loop, Cupertino, California 90210',
      deliveryType: 'Free Shipping',
      status: 'Pending',
      badge: { type: 'warning', icon: 'fas fa-stream' },
      amount: '$92'
    },
    {
      id: 5,
      dropdownId: 'order-dropdown-5',
      orderId: '#2185',
      mailLink: 'mailto:josef@example.com',
      customer: 'Josef Stravinsky',
      date: '30/04/2023',
      address: 'Josef Stravinsky, 1 Infinite Loop, Cupertino, California 90210',
      deliveryType: 'Via Free Road',
      status: 'On Hold',
      badge: { type: 'secondary', icon: 'fas fa-ban' },
      amount: '$120'
    },
    {
      id: 6,
      dropdownId: 'order-dropdown-6',
      orderId: '#2186',
      mailLink: 'mailto:igor@example.com',
      customer: 'Igor Borvibson',
      date: '30/04/2023',
      address: 'Igor Borvibson, 1 Infinite Loop, Cupertino, California 90210',
      deliveryType: 'Free Shipping',
      status: 'Processing',
      badge: { type: 'primary', icon: 'fas fa-redo' },
      amount: '$145'
    },
    {
      id: 7,
      dropdownId: 'order-dropdown-7',
      orderId: '#2187',
      mailLink: 'mailto:katerina@example.com',
      customer: 'Katerina Karenin',
      date: '30/04/2023',
      address: 'Katerina Karenin, 1 Infinite Loop, Cupertino, California 90210',
      deliveryType: 'Flat Rate',
      status: 'Completed',
      badge: { type: 'success', icon: 'fas fa-check' },
      amount: '$55'
    },
    {
      id: 8,
      dropdownId: 'order-dropdown-8',
      orderId: '#2188',
      mailLink: 'mailto:roy@example.com',
      customer: 'Roy Anderson',
      date: '29/04/2023',
      address: 'Roy Anderson, 1 Infinite Loop, Cupertino, California 90210',
      deliveryType: 'Local Delivery',
      status: 'On Hold',
      badge: { type: 'secondary', icon: 'fas fa-ban' },
      amount: '$90'
    },
    {
      id: 9,
      dropdownId: 'order-dropdown-9',
      orderId: '#2189',
      mailLink: 'mailto:Stephenson@example.com',
      customer: 'Thomas Stephenson',
      date: '29/04/2023',
      address: 'Thomas Stephenson, 116 Ballifeary Road, Bamff',
      deliveryType: 'Flat Rate',
      status: 'Processing',
      badge: { type: 'primary', icon: 'fas fa-redo' },
      amount: '$52'
    },
    {
      id: 10,
      dropdownId: 'order-dropdown-10',
      orderId: '#2190',
      mailLink: 'mailto:eviewsing@example.com',
      customer: 'Evie Singh',
      date: '29/04/2023',
      address: 'Evie Singh, 54 Castledore Road, Tunstead',
      deliveryType: 'Flat Rate',
      status: 'Completed',
      badge: { type: 'success', icon: 'fas fa-check' },
      amount: '$90'
    },
    {
      id: 11,
      dropdownId: 'order-dropdown-11',
      orderId: '#2191',
      mailLink: 'mailto:peter@example.com',
      customer: 'David Peters',
      date: '29/04/2023',
      address: 'David Peters, Rhyd Y Groes, Rhosgoch, LL66 0AT',
      deliveryType: 'Local Delivery',
      status: 'Completed',
      badge: { type: 'success', icon: 'fas fa-check' },
      amount: '$69'
    },
    {
      id: 12,
      dropdownId: 'order-dropdown-12',
      orderId: '#2192',
      mailLink: 'mailto:jennifer@example.com',
      customer: 'Jennifer Johnson',
      date: '28/04/2023',
      address: 'Jennifer Johnson, Rhyd Y Groes, Rhosgoch, LL66 0AT',
      deliveryType: 'Flat Rate',
      status: 'Processing',
      badge: { type: 'primary', icon: 'fas fa-redo' },
      amount: '$112'
    },
    {
      id: 13,
      dropdownId: 'order-dropdown-13',
      orderId: '#2193',
      mailLink: 'mailto:okuneva@example.com',
      customer: 'Demarcus Okuneva',
      date: '28/04/2023',
      address: 'Demarcus Okuneva, 90555 Upton Drive Jeffreyview, UT 08771',
      deliveryType: 'Flat Rate',
      status: 'Completed',
      badge: { type: 'success', icon: 'fas fa-check' },
      amount: '$99'
    },
    {
      id: 14,
      dropdownId: 'order-dropdown-14',
      orderId: '#2194',
      mailLink: 'mailto:simeon@example.com',
      customer: 'Simeon Harber',
      date: '27/04/2023',
      address:
        'Simeon Harber, 702 Kunde Plain Apt. 634 East Bridgetview, HI 13134-1862',
      deliveryType: 'Free Shipping',
      status: 'On Hold',
      badge: { type: 'secondary', icon: 'fas fa-ban' },
      amount: '$129'
    },
    {
      id: 15,
      dropdownId: 'order-dropdown-15',
      orderId: '#2195',
      mailLink: 'mailto:lavon@example.com',
      customer: 'Lavon Haley',
      date: '27/04/2023',
      address: 'Lavon Haley, 30998 Adonis Locks McGlynnside, ID 27241',
      deliveryType: 'Free Shipping',
      status: 'Pending',
      badge: { type: 'warning', icon: 'fas fa-stream' },
      amount: '$70'
    },
    {
      id: 16,
      dropdownId: 'order-dropdown-16',
      orderId: '#2196',
      mailLink: 'mailto:ashley@example.com',
      customer: 'Ashley Kirlin',
      date: '26/04/2023',
      address:
        'Ashley Kirlin, 43304 Prosacco Shore South Dejuanfurt, MO 18623-0505',
      deliveryType: 'Local Delivery',
      status: 'Processing',
      badge: { type: 'primary', icon: 'fas fa-redo' },
      amount: '$39'
    },
    {
      id: 17,
      dropdownId: 'order-dropdown-17',
      orderId: '#2197',
      mailLink: 'mailto:johnnie@example.com',
      customer: 'Johnnie Considine',
      date: '26/04/2023',
      address:
        'Johnnie Considine, 6008 Hermann Points Suite 294 Hansenville, TN 14210',
      deliveryType: 'Flat Rate',
      status: 'Pending',
      badge: { type: 'warning', icon: 'fas fa-stream' },
      amount: '$70'
    },
    {
      id: 18,
      dropdownId: 'order-dropdown-18',
      orderId: '#2198',
      mailLink: 'mailto:trace@example.com',
      customer: 'Trace Farrell',
      date: '26/04/2023',
      address: 'Trace Farrell, 431 Steuber Mews Apt. 252 Germanland, AK 25882',
      deliveryType: 'Free Shipping',
      status: 'Completed',
      badge: { type: 'success', icon: 'fas fa-check' },
      amount: '$70'
    },
    {
      id: 19,
      dropdownId: 'order-dropdown-19',
      orderId: '#2199',
      mailLink: 'mailto:nienow@example.com',
      customer: 'Estell Nienow',
      date: '26/04/2023',
      address: 'Estell Nienow, 4167 Laverna Manor Marysemouth, NV 74590',
      deliveryType: 'Free Shipping',
      status: 'Completed',
      badge: { type: 'success', icon: 'fas fa-check' },
      amount: '$59'
    },
    {
      id: 20,
      dropdownId: 'order-dropdown-20',
      orderId: '#2200',
      mailLink: 'mailto:howe@example.com',
      customer: 'Daisha Howe',
      date: '25/04/2023',
      address:
        'Daisha Howe, 829 Lavonne Valley Apt. 074 Stehrfort, RI 77914-0379',
      deliveryType: 'Free Shipping',
      status: 'Completed',
      badge: { type: 'success', icon: 'fas fa-check' },
      amount: '$39'
    },
    {
      id: 21,
      dropdownId: 'order-dropdown-21',
      orderId: '#2201',
      mailLink: 'mailto:haley@example.com',
      customer: 'Miles Haley',
      date: '24/04/2023',
      address: 'Miles Haley, 53150 Thad Squares Apt. 263 Archibaldfort, MO 00837',
      deliveryType: 'Flat Rate',
      status: 'Completed',
      badge: { type: 'success', icon: 'fas fa-check' },
      amount: '$55'
    },
    {
      id: 22,
      dropdownId: 'order-dropdown-22',
      orderId: '#2202',
      mailLink: 'mailto:watsica@example.com',
      customer: 'Brenda Watsica',
      date: '24/04/2023',
      address: "Brenda Watsica, 9198 O'Kon Harbors Morarborough, IA 75409-7383",
      deliveryType: 'Free Shipping',
      status: 'Completed',
      badge: { type: 'success', icon: 'fas fa-check' },
      amount: '$89'
    },
    {
      id: 23,
      dropdownId: 'order-dropdown-23',
      orderId: '#2203',
      mailLink: 'mailto:ellie@example.com',
      customer: "Ellie O'Reilly",
      date: '24/04/2023',
      address:
        "Ellie O'Reilly, 1478 Kaitlin Haven Apt. 061 Lake Muhammadmouth, SC 35848",
      deliveryType: 'Free Shipping',
      status: 'Completed',
      badge: { type: 'success', icon: 'fas fa-check' },
      amount: '$47'
    },
    {
      id: 24,
      dropdownId: 'order-dropdown-24',
      orderId: '#2204',
      mailLink: 'mailto:garry@example.com',
      customer: 'Garry Brainstrow',
      date: '23/04/2023',
      address: 'Garry Brainstrow, 13572 Kurt Mews South Merritt, IA 52491',
      deliveryType: 'Free Shipping',
      status: 'Completed',
      badge: { type: 'success', icon: 'fas fa-check' },
      amount: '$139'
    },
    {
      id: 25,
      dropdownId: 'order-dropdown-25',
      orderId: '#2205',
      mailLink: 'mailto:estell@example.com',
      customer: 'Estell Pollich',
      date: '23/04/2023',
      address: 'Estell Pollich, 13572 Kurt Mews South Merritt, IA 52491',
      deliveryType: 'Free Shipping',
      status: 'On Hold',
      badge: { type: 'secondary', icon: 'fas fa-ban' },
      amount: '$49'
    },
    {
      id: 26,
      dropdownId: 'order-dropdown-26',
      orderId: '#2206',
      mailLink: 'mailto:ara@example.com',
      customer: 'Ara Mueller',
      date: '23/04/2023',
      address: 'Ara Mueller, 91979 Kohler Place Waelchiborough, CT 41291',
      deliveryType: 'Flat Rate',
      status: 'On Hold',
      badge: { type: 'secondary', icon: 'fas fa-ban' },
      amount: '$19'
    },
    {
      id: 27,
      dropdownId: 'order-dropdown-27',
      orderId: '#2207',
      mailLink: 'mailto:blick@example.com',
      customer: 'Lucienne Blick',
      date: '23/04/2023',
      address:
        'Lucienne Blick, 6757 Giuseppe Meadows Geraldinemouth, MO 48819-4970',
      deliveryType: 'Flat Rate',
      status: 'On Hold',
      badge: { type: 'secondary', icon: 'fas fa-ban' },
      amount: '$59'
    },
    {
      id: 28,
      dropdownId: 'order-dropdown-28',
      orderId: '#2208',
      mailLink: 'mailto:haag@example.com',
      customer: 'Laverne Haag',
      date: '22/04/2023',
      address: 'Laverne Haag, 2327 Kaylee Mill East Citlalli, AZ 89582-3143',
      deliveryType: 'Flat Rate',
      status: 'On Hold',
      badge: { type: 'secondary', icon: 'fas fa-ban' },
      amount: '$49'
    },
    {
      id: 29,
      dropdownId: 'order-dropdown-29',
      orderId: '#2209',
      mailLink: 'mailto:bednar@example.com',
      customer: 'Brandon Bednar',
      date: '22/04/2023',
      address:
        'Brandon Bednar, 25156 Isaac Crossing Apt. 810 Lonborough, CO 83774-5999',
      deliveryType: 'Flat Rate',
      status: 'On Hold',
      badge: { type: 'secondary', icon: 'fas fa-ban' },
      amount: '$39'
    },
    {
      id: 30,
      dropdownId: 'order-dropdown-30',
      orderId: '#2210',
      mailLink: 'mailto:dimitri@example.com',
      customer: 'Dimitri Boehm',
      date: '23/04/2023',
      address: 'Dimitri Boehm, 71603 Wolff Plains Apt. 885 Johnstonton, MI 01581',
      deliveryType: 'Flat Rate',
      status: 'On Hold',
      badge: { type: 'secondary', icon: 'fas fa-ban' },
      amount: '$111'
    }
  ];

  const advanceAjaxTableInit = () => {
    const togglePaginationButtonDisable = (button, disabled) => {
      button.disabled = disabled;
      button.classList[disabled ? 'add' : 'remove']('disabled');
    };
    // Selectors
    const table = document.getElementById('advanceAjaxTable');

    if (table) {
      const options = {
        page: 10,
        pagination: {
          item: "<li><button class='page' type='button'></button></li>"
        },
        item: values => {
          const {
            orderId,
            id,
            customer,
            date,
            address,
            deliveryType,
            status,
            badge,
            amount
          } = values;
          return `
          <tr class="btn-reveal-trigger">
            <td class="order py-2  ps-3 align-middle white-space-nowrap">
              <a class="fw-semibold" href="https://prium.github.io/phoenix/v1.12.0/apps/e-commerce/admin/order-details.html">
                ${orderId}
              </a>
            </td>
            <td class="py-2 align-middle fw-bold">
              <a class="fw-semibold text-body" href="#!">
                ${customer}
              </a>
            </td>
            <td class="py-2 align-middle">
              ${date}
            </td>
            <td class="py-2 align-middle white-space-nowrap">
              ${address}
            </td>
            <td class="py-2 align-middle white-space-nowrap">
              <p class="mb-0">${deliveryType}</p>
            </td>
            <td class="py-2 align-middle text-center fs-8 white-space-nowrap">
              <span class="badge fs-10 badge-phoenix badge-phoenix-${badge.type}">
                ${status}
                <span class="ms-1 ${badge.icon}" data-fa-transform="shrink-2"></span>
              </span>
            </td>
            <td class="py-2 align-middle text-end fs-8 fw-medium">
              ${amount}
            </td>
            <td class="py-2 align-middle white-space-nowrap text-end">
              <div class="dropstart position-static d-inline-block">
                <button class="btn btn-link text-body btn-sm dropdown-toggle btn-reveal" type='button' id="order-dropdown-${id}" data-bs-toggle="dropdown" data-boundary="window" aria-haspopup="true" aria-expanded="false" data-bs-reference="parent">
                  <span class="fas fa-ellipsis-h fs-9"></span>
                </button>
                <div class="dropdown-menu dropdown-menu-end border py-2" aria-labelledby="order-dropdown-${id}">
                  <a href="#!" class="dropdown-item">View</a>
                  <a href="#!" class="dropdown-item">Edit</a>
                  <div class"dropdown-divider"></div>
                  <a href="#!" class="dropdown-item text-warning">Archive</a>
                </div>
              </div>
            </td>
          </tr>
        `;
        }
      };
      const paginationButtonNext = table.querySelector(
        '[data-list-pagination="next"]'
      );
      const paginationButtonPrev = table.querySelector(
        '[data-list-pagination="prev"]'
      );
      const viewAll = table.querySelector('[data-list-view="*"]');
      const viewLess = table.querySelector('[data-list-view="less"]');
      const listInfo = table.querySelector('[data-list-info]');
      const listFilter = document.querySelector('[data-list-filter]');

      const orderList = new window.List(table, options, orders);

      // Fallback
      orderList.on('updated', item => {
        const fallback =
          table.querySelector('.fallback') ||
          document.getElementById(options.fallback);

        if (fallback) {
          if (item.matchingItems.length === 0) {
            fallback.classList.remove('d-none');
          } else {
            fallback.classList.add('d-none');
          }
        }
      });

      const totalItem = orderList.items.length;
      const itemsPerPage = orderList.page;
      const btnDropdownClose =
        orderList.listContainer.querySelector('.btn-close');
      let pageQuantity = Math.ceil(totalItem / itemsPerPage);
      let numberOfcurrentItems = orderList.visibleItems.length;
      let pageCount = 1;

      btnDropdownClose &&
        btnDropdownClose.addEventListener('search.close', () =>
          orderList.fuzzySearch('')
        );

      const updateListControls = () => {
        listInfo &&
          (listInfo.innerHTML = `${orderList.i} to ${numberOfcurrentItems} of ${totalItem}`);
        paginationButtonPrev &&
          togglePaginationButtonDisable(paginationButtonPrev, pageCount === 1);
        paginationButtonNext &&
          togglePaginationButtonDisable(
            paginationButtonNext,
            pageCount === pageQuantity
          );

        if (pageCount > 1 && pageCount < pageQuantity) {
          togglePaginationButtonDisable(paginationButtonNext, false);
          togglePaginationButtonDisable(paginationButtonPrev, false);
        }
      };
      updateListControls();

      if (paginationButtonNext) {
        paginationButtonNext.addEventListener('click', e => {
          e.preventDefault();
          pageCount += 1;

          const nextInitialIndex = orderList.i + itemsPerPage;
          nextInitialIndex <= orderList.size() &&
            orderList.show(nextInitialIndex, itemsPerPage);
          numberOfcurrentItems += orderList.visibleItems.length;
          updateListControls();
        });
      }

      if (paginationButtonPrev) {
        paginationButtonPrev.addEventListener('click', e => {
          e.preventDefault();
          pageCount -= 1;

          numberOfcurrentItems -= orderList.visibleItems.length;
          const prevItem = orderList.i - itemsPerPage;
          prevItem > 0 && orderList.show(prevItem, itemsPerPage);
          updateListControls();
        });
      }

      const toggleViewBtn = () => {
        viewLess.classList.toggle('d-none');
        viewAll.classList.toggle('d-none');
      };

      if (viewAll) {
        viewAll.addEventListener('click', () => {
          orderList.show(1, totalItem);
          pageQuantity = 1;
          pageCount = 1;
          numberOfcurrentItems = totalItem;
          updateListControls();
          toggleViewBtn();
        });
      }
      if (viewLess) {
        viewLess.addEventListener('click', () => {
          orderList.show(1, itemsPerPage);
          pageQuantity = Math.ceil(totalItem / itemsPerPage);
          pageCount = 1;
          numberOfcurrentItems = orderList.visibleItems.length;
          updateListControls();
          toggleViewBtn();
        });
      }
      if (options.pagination) {
        table.querySelector('.pagination').addEventListener('click', e => {
          if (e.target.classList[0] === 'page') {
            pageCount = Number(e.target.innerText);
            updateListControls();
          }
        });
      }
      if (options.filter) {
        const { key } = options.filter;
        listFilter.addEventListener('change', e => {
          orderList.filter(item => {
            if (e.target.value === '') {
              return true;
            }
            return item
              .values()
              [key].toLowerCase()
              .includes(e.target.value.toLowerCase());
          });
        });
      }
    }
  };

  // import AnchorJS from 'anchor-js';

  const anchorJSInit = () => {
    const anchors = new window.AnchorJS({
      icon: '#'
    });
    anchors.add('[data-anchor]');
  };

  /* -------------------------------------------------------------------------- */
  /*                                 bigPicture                                 */
  /* -------------------------------------------------------------------------- */
  const bigPictureInit = () => {
    const { getData } = window.phoenix.utils;
    if (window.BigPicture) {
      const bpItems = document.querySelectorAll('[data-bigpicture]');
      bpItems.forEach(bpItem => {
        const userOptions = getData(bpItem, 'bigpicture');
        const defaultOptions = {
          el: bpItem,
          noLoader: true,
          allowfullscreen: true
        };
        const options = window._.merge(defaultOptions, userOptions);

        bpItem.addEventListener('click', () => {
          window.BigPicture(options);
        });
      });
    }
  };

  /* eslint-disable no-unused-expressions */
  /*-----------------------------------------------
  |   DomNode
  -----------------------------------------------*/
  class DomNode {
    constructor(node) {
      this.node = node;
    }

    addClass(className) {
      this.isValidNode() && this.node.classList.add(className);
    }

    removeClass(className) {
      this.isValidNode() && this.node.classList.remove(className);
    }

    toggleClass(className) {
      this.isValidNode() && this.node.classList.toggle(className);
    }

    hasClass(className) {
      this.isValidNode() && this.node.classList.contains(className);
    }

    data(key) {
      if (this.isValidNode()) {
        try {
          return JSON.parse(this.node.dataset[this.camelize(key)]);
        } catch (e) {
          return this.node.dataset[this.camelize(key)];
        }
      }
      return null;
    }

    attr(name) {
      return this.isValidNode() && this.node[name];
    }

    setAttribute(name, value) {
      this.isValidNode() && this.node.setAttribute(name, value);
    }

    removeAttribute(name) {
      this.isValidNode() && this.node.removeAttribute(name);
    }

    setProp(name, value) {
      this.isValidNode() && (this.node[name] = value);
    }

    on(event, cb) {
      this.isValidNode() && this.node.addEventListener(event, cb);
    }

    isValidNode() {
      return !!this.node;
    }

    // eslint-disable-next-line class-methods-use-this
    camelize(str) {
      const text = str.replace(/[-_\s.]+(.)?/g, (_, c) =>
        c ? c.toUpperCase() : ''
      );
      return `${text.substr(0, 1).toLowerCase()}${text.substr(1)}`;
    }
  }

  /*-----------------------------------------------
  |   Bulk Select
  -----------------------------------------------*/

  const elementMap = new Map();

  class BulkSelect {
    constructor(element, option) {
      this.element = element;
      this.option = {
        displayNoneClassName: 'd-none',
        ...option
      };
      elementMap.set(this.element, this);
    }

    // Static
    static getInstance(element) {
      if (elementMap.has(element)) {
        return elementMap.get(element);
      }
      return null;
    }

    init() {
      this.attachNodes();
      this.clickBulkCheckbox();
      this.clickRowCheckbox();
    }

    getSelectedRows() {
      return Array.from(this.bulkSelectRows)
        .filter(row => row.checked)
        .map(row => getData(row, 'bulk-select-row'));
    }

    attachNodes() {
      const { body, actions, replacedElement } = getData(
        this.element,
        'bulk-select'
      );

      this.actions = new DomNode(document.getElementById(actions));
      this.replacedElement = new DomNode(
        document.getElementById(replacedElement)
      );
      this.bulkSelectRows = document
        .getElementById(body)
        .querySelectorAll('[data-bulk-select-row]');
    }

    attachRowNodes(elms) {
      this.bulkSelectRows = elms;
    }

    clickBulkCheckbox() {
      // Handle click event in bulk checkbox
      this.element.addEventListener('click', () => {
        if (this.element.indeterminate === 'indeterminate') {
          this.actions.addClass(this.option.displayNoneClassName);
          this.replacedElement.removeClass(this.option.displayNoneClassName);

          this.removeBulkCheck();

          this.bulkSelectRows.forEach(el => {
            const rowCheck = new DomNode(el);
            rowCheck.checked = false;
            rowCheck.setAttribute('checked', false);
          });
          return;
        }

        this.toggleDisplay();
        this.bulkSelectRows.forEach(el => {
          el.checked = this.element.checked;
        });
      });
    }

    clickRowCheckbox() {
      // Handle click event in checkbox of each row
      this.bulkSelectRows.forEach(el => {
        const rowCheck = new DomNode(el);
        rowCheck.on('click', () => {
          if (this.element.indeterminate !== 'indeterminate') {
            this.element.indeterminate = true;
            this.element.setAttribute('indeterminate', 'indeterminate');
            this.element.checked = true;
            this.element.setAttribute('checked', true);

            this.actions.removeClass(this.option.displayNoneClassName);
            this.replacedElement.addClass(this.option.displayNoneClassName);
          }

          if ([...this.bulkSelectRows].every(element => element.checked)) {
            this.element.indeterminate = false;
            this.element.setAttribute('indeterminate', false);
          }

          if ([...this.bulkSelectRows].every(element => !element.checked)) {
            this.removeBulkCheck();
            this.toggleDisplay();
          }
        });
      });
    }

    removeBulkCheck() {
      this.element.indeterminate = false;
      this.element.removeAttribute('indeterminate');
      this.element.checked = false;
      this.element.setAttribute('checked', false);
    }

    toggleDisplay() {
      this.actions.toggleClass(this.option.displayNoneClassName);
      this.replacedElement.toggleClass(this.option.displayNoneClassName);
    }
  }

  const bulkSelectInit = () => {
    const bulkSelects = document.querySelectorAll('[data-bulk-select]');

    if (bulkSelects.length) {
      bulkSelects.forEach(el => {
        const bulkSelect = new BulkSelect(el);
        bulkSelect.init();
      });
    }
  };

  // import * as echarts from 'echarts';
  const { merge: merge$2 } = window._;

  // form config.js
  const echartSetOption = (
    chart,
    userOptions,
    getDefaultOptions,
    responsiveOptions
  ) => {
    const { breakpoints, resize } = window.phoenix.utils;
    const handleResize = options => {
      Object.keys(options).forEach(item => {
        if (window.innerWidth > breakpoints[item]) {
          chart.setOption(options[item]);
        }
      });
    };

    const themeController = document.body;
    // Merge user options with lodash
    chart.setOption(merge$2(getDefaultOptions(), userOptions));

    const navbarVerticalToggle = document.querySelector(
      '.navbar-vertical-toggle'
    );
    if (navbarVerticalToggle) {
      navbarVerticalToggle.addEventListener('navbar.vertical.toggle', () => {
        chart.resize();
        if (responsiveOptions) {
          handleResize(responsiveOptions);
        }
      });
    }

    resize(() => {
      chart.resize();
      if (responsiveOptions) {
        handleResize(responsiveOptions);
      }
    });
    if (responsiveOptions) {
      handleResize(responsiveOptions);
    }

    themeController.addEventListener(
      'clickControl',
      ({ detail: { control } }) => {
        if (control === 'phoenixTheme') {
          chart.setOption(window._.merge(getDefaultOptions(), userOptions));
        }
        if (responsiveOptions) {
          handleResize(responsiveOptions);
        }
      }
    );
  };
  // -------------------end config.js--------------------

  const echartTabs = document.querySelectorAll('[data-tab-has-echarts]');
  if (echartTabs) {
    echartTabs.forEach(tab => {
      tab.addEventListener('shown.bs.tab', e => {
        const el = e.target;
        const { hash } = el;
        const id = hash || el.dataset.bsTarget;
        const content = document.getElementById(id.substring(1));
        const chart = content?.querySelector('[data-echart-tab]');
        if (chart) {
          window.echarts.init(chart).resize();
        }
      });
    });
  }

  const handleTooltipPosition = ([pos, , dom, , size]) => {
    // only for mobile device
    if (window.innerWidth <= 540) {
      const tooltipHeight = dom.offsetHeight;
      const obj = { top: pos[1] - tooltipHeight - 20 };
      obj[pos[0] < size.viewSize[0] / 2 ? 'left' : 'right'] = 5;
      return obj;
    }
    return null; // else default behaviour
  };

  // import dayjs from 'dayjs';
  /* -------------------------------------------------------------------------- */
  /*                     Echart Bar Member info                                 */
  /* -------------------------------------------------------------------------- */

  const basicEchartsInit = () => {
    const { getColor, getData, getDates } = window.phoenix.utils;

    const $echartBasicCharts = document.querySelectorAll('[data-echarts]');
    $echartBasicCharts.forEach($echartBasicChart => {
      const userOptions = getData($echartBasicChart, 'echarts');
      const chart = window.echarts.init($echartBasicChart);
      const getDefaultOptions = () => ({
        color: getColor('primary'),
        tooltip: {
          trigger: 'item',
          padding: [7, 10],
          backgroundColor: getColor('body-highlight-bg'),
          borderColor: getColor('border-color'),
          textStyle: { color: getColor('light-text-emphasis') },
          borderWidth: 1,
          transitionDuration: 0,
          extraCssText: 'z-index: 1000'
        },
        xAxis: {
          type: 'category',
          data: getDates(
            new Date('5/1/2022'),
            new Date('5/7/2022'),
            1000 * 60 * 60 * 24
          ),
          show: true,
          boundaryGap: false,
          axisLine: {
            show: true,
            lineStyle: { color: getColor('secondary-bg') }
          },
          axisTick: {
            show: false
          },
          axisLabel: {
            formatter: value => window.dayjs(value).format('DD MMM'),
            interval: 6,
            showMinLabel: true,
            showMaxLabel: true,
            color: getColor('secondary-color')
          }
        },
        yAxis: {
          show: false,
          type: 'value',
          boundaryGap: false
        },
        series: [
          {
            type: 'bar',
            symbol: 'none'
          }
        ],
        grid: { left: 22, right: 22, top: 0, bottom: 20 }
      });
      echartSetOption(chart, userOptions, getDefaultOptions);
    });
  };

  /* -------------------------------------------------------------------------- */
  /*                             Echarts Total Sales                            */
  /* -------------------------------------------------------------------------- */

  const reportsDetailsChartInit = () => {
    const { getColor, getData, toggleColor } = window.phoenix.utils;
    // const phoenixTheme = window.config.config;
    const $chartEl = document.querySelector('.echart-reports-details');

    const tooltipFormatter = (params, dateFormatter = 'MMM DD') => {
      let tooltipItem = ``;
      params.forEach(el => {
        tooltipItem += `<div class='ms-1'>
          <h6 class="text-body-tertiary"><span class="fas fa-circle me-1 fs-10" style="color:${
            el.color
          }"></span>
            ${el.seriesName} : ${
        typeof el.value === 'object' ? el.value[1] : el.value
      }
          </h6>
        </div>`;
      });
      return `<div>
              <p class='mb-2 text-body-tertiary'>
                ${
                  window.dayjs(params[0].axisValue).isValid()
                    ? window.dayjs(params[0].axisValue).format('DD MMM, YYYY')
                    : params[0].axisValue
                }
              </p>
              ${tooltipItem}
            </div>`;
    };

    // const dates = getPastDates(7);
    const data = [64, 40, 45, 62, 82];

    if ($chartEl) {
      const userOptions = getData($chartEl, 'echarts');
      const chart = window.echarts.init($chartEl);

      const getDefaultOptions = () => ({
        color: [getColor('primary-lighter'), getColor('info-light')],
        tooltip: {
          trigger: 'axis',
          padding: [7, 10],
          backgroundColor: getColor('body-highlight-bg'),
          borderColor: getColor('border-color'),
          textStyle: { color: getColor('light-text-emphasis') },
          borderWidth: 1,
          transitionDuration: 0,
          axisPointer: {
            type: 'none'
          },
          formatter: tooltipFormatter,
          extraCssText: 'z-index: 1000'
        },
        // legend: {
        //   left: '76%',
        //   top: 'auto',
        //   icon: 'circle',
        // },
        xAxis: {
          type: 'category',
          data: ['Analysis', 'Statement', 'Action', 'Offering', 'Interlocution'],
          axisLabel: {
            color: getColor('body-color'),
            fontFamily: 'Nunito Sans',
            fontWeight: 600,
            fontSize: 12.8,
            rotate: 30,
            formatter: value => `${value.slice(0, 5)}...`
          },
          axisLine: {
            lineStyle: {
              color: getColor('secondary-bg')
            }
          },
          axisTick: false
        },
        yAxis: {
          type: 'value',
          splitLine: {
            lineStyle: {
              color: getColor('secondary-bg')
            }
          },
          // splitLine: {
          //   show: true,
          //   lineStyle: {
          //     color: "rgba(217, 21, 21, 1)"
          //   }
          // },
          axisLabel: {
            color: getColor('body-color'),
            fontFamily: 'Nunito Sans',
            fontWeight: 700,
            fontSize: 12.8,
            margin: 24,
            formatter: value => `${value}%`
          }
        },
        series: [
          {
            name: 'Revenue',
            type: 'bar',
            barWidth: '32px',
            barGap: '48%',
            showBackground: true,
            backgroundStyle: {
              color: toggleColor(
                getColor('primary-bg-subtle'),
                getColor('body-highlight-bg')
              )
            },
            label: {
              show: false
            },
            itemStyle: {
              color: toggleColor(getColor('primary-light'), getColor('primary'))
            },
            data
          }
        ],
        grid: {
          right: '0',
          left: '0',
          bottom: 0,
          top: 10,
          containLabel: true
        },
        animation: false
      });

      echartSetOption(chart, userOptions, getDefaultOptions);
    }
  };

  /*-----------------------------------------------
  |   Chat
  -----------------------------------------------*/
  const chatInit = () => {
    const { getData } = window.phoenix.utils;

    const Selector = {
      CHAT_SIDEBAR: '.chat-sidebar',
      CHAT_TEXT_AREA: '.chat-textarea',
      CHAT_THREADS: '[data-chat-thread]',
      CHAT_THREAD_TAB: '[data-chat-thread-tab]',
      CHAT_THREAD_TAB_CONTENT: '[data-chat-thread-tab-content]'
    };

    const $chatSidebar = document.querySelector(Selector.CHAT_SIDEBAR);
    const $chatTextArea = document.querySelector(Selector.CHAT_TEXT_AREA);
    const $chatThreads = document.querySelectorAll(Selector.CHAT_THREADS);
    const threadTab = document.querySelector(Selector.CHAT_THREAD_TAB);
    const threadTabContent = document.querySelector(
      Selector.CHAT_THREAD_TAB_CONTENT
    );

    if (threadTab) {
      const threadTabItems = threadTab.querySelectorAll("[data-bs-toggle='tab']");

      const list = new window.List(threadTabContent, {
        valueNames: ['read', 'unreadItem']
      });

      const chatBox = document.querySelector('.chat .card-body');
      chatBox.scrollTop = chatBox.scrollHeight;

      threadTabItems.forEach(tabEl =>
        tabEl.addEventListener('shown.bs.tab', () => {
          const value = getData(tabEl, 'chat-thread-list');
          list.filter(item => {
            if (value === 'all') {
              return true;
            }
            return item.elm.classList.contains(value);
          });
        })
      );
    }

    $chatThreads.forEach((thread, index) => {
      thread.addEventListener('click', () => {
        const chatContentArea = document.querySelector(
          `.chat-content-body-${index}`
        );
        chatContentArea.scrollTop = chatContentArea.scrollHeight;
        $chatSidebar.classList.remove('show');
        if (thread.classList.contains('unread')) {
          thread.classList.remove('unread');
          const unreadBadge = thread.querySelector('.unread-badge');
          if (unreadBadge) {
            unreadBadge.remove();
          }
        }
      });
    });

    if ($chatTextArea) {
      $chatTextArea.setAttribute('placeholder', 'Type your message...');
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                                   choices                                   */
  /* -------------------------------------------------------------------------- */
  const choicesInit = () => {
    const { getData } = window.phoenix.utils;

    if (window.Choices) {
      const elements = document.querySelectorAll('[data-choices]');
      elements.forEach(item => {
        const userOptions = getData(item, 'options');
        const choices = new window.Choices(item, {
          itemSelectText: '',
          addItems: true,
          ...userOptions
        });

        const needsValidation = document.querySelectorAll('.needs-validation');

        needsValidation.forEach(validationItem => {
          const selectFormValidation = () => {
            validationItem.querySelectorAll('.choices').forEach(choicesItem => {
              const singleSelect = choicesItem.querySelector(
                '.choices__list--single'
              );
              const multipleSelect = choicesItem.querySelector(
                '.choices__list--multiple'
              );

              if (choicesItem.querySelector('[required]')) {
                if (singleSelect) {
                  if (
                    singleSelect
                      .querySelector('.choices__item--selectable')
                      ?.getAttribute('data-value') !== ''
                  ) {
                    choicesItem.classList.remove('invalid');
                    choicesItem.classList.add('valid');
                  } else {
                    choicesItem.classList.remove('valid');
                    choicesItem.classList.add('invalid');
                  }
                }
                // ----- for multiple select only ----------
                if (multipleSelect) {
                  if (choicesItem.getElementsByTagName('option').length) {
                    choicesItem.classList.remove('invalid');
                    choicesItem.classList.add('valid');
                  } else {
                    choicesItem.classList.remove('valid');
                    choicesItem.classList.add('invalid');
                  }
                }

                // ------ select end ---------------
              }
            });
          };

          validationItem.addEventListener('submit', () => {
            selectFormValidation();
          });

          item.addEventListener('change', () => {
            selectFormValidation();
          });
        });

        return choices;
      });
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                                  Copy LinK                                 */
  /* -------------------------------------------------------------------------- */

  const copyLink = () => {
    const { getData } = window.phoenix.utils;

    const copyButtons = document.querySelectorAll('[data-copy]');

    copyButtons.forEach(button => {
      const tooltip = new window.bootstrap.Tooltip(button);

      button.addEventListener('mouseover', () => tooltip.show());
      button.addEventListener('mouseleave', () => tooltip.hide());

      button.addEventListener('click', () => {
        button.setAttribute('data-bs-original-title', 'Copied');
        tooltip.show();
        const inputID = getData(button, 'copy');
        const input = document.querySelector(inputID);
        input.select();
        navigator.clipboard.writeText(input.value);
        button.setAttribute('data-bs-original-title', 'click to copy');
      });
    });
  };

  /* -------------------------------------------------------------------------- */
  /*                                  Count Up                                  */
  /* -------------------------------------------------------------------------- */

  const countupInit = () => {
    const { getData } = window.phoenix.utils;
    if (window.countUp) {
      const countups = document.querySelectorAll('[data-countup]');
      countups.forEach(node => {
        const { endValue, ...options } = getData(node, 'countup');
        const countUp = new window.countUp.CountUp(node, endValue, {
          duration: 4,
          // suffix: '+',

          ...options
        });
        if (!countUp.error) {
          countUp.start();
        } else {
          console.error(countUp.error);
        }
      });
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                                 step wizard                                */
  /* -------------------------------------------------------------------------- */
  const createBoardInit = () => {
    const { getData } = window.phoenix.utils;
    const selectors = {
      CREATE_BOARD: '[data-create-board]',
      TOGGLE_BUTTON_EL: '[data-wizard-step]',
      FORMS: '[data-wizard-form]',
      PASSWORD_INPUT: '[data-wizard-password]',
      CONFIRM_PASSWORD_INPUT: '[data-wizard-confirm-password]',
      NEXT_BTN: '[data-wizard-next-btn]',
      PREV_BTN: '[data-wizard-prev-btn]',
      FOOTER: '[data-wizard-footer]',
      KANBAN_STEP: '[data-kanban-step]',
      BOARD_PREV_BTN: '[data-board-prev-btn]',
      CUSTOM_COLOR: '[data-custom-color-radio]'
    };

    const events = {
      SUBMIT: 'submit',
      SHOW: 'show.bs.tab',
      SHOWN: 'shown.bs.tab',
      CLICK: 'click',
      CHANGE: 'change'
    };

    const createBoard = document.querySelector(selectors.CREATE_BOARD);
    if (createBoard) {
      const tabToggleButtonEl = createBoard.querySelectorAll(
        selectors.TOGGLE_BUTTON_EL
      );
      const tabs = Array.from(tabToggleButtonEl).map(item => {
        return window.bootstrap.Tab.getOrCreateInstance(item);
      });

      // previous button only for create board last step
      const boardPrevButton = document.querySelector(selectors.BOARD_PREV_BTN);
      boardPrevButton?.addEventListener(events.CLICK, () => {
        tabs[tabs.length - 2].show();
      });

      // update kanban step
      if (tabToggleButtonEl.length) {
        tabToggleButtonEl.forEach(item => {
          item.addEventListener(events.SHOW, () => {
            const step = getData(item, 'wizard-step');
            const kanbanStep = document.querySelector(selectors.KANBAN_STEP);
            if (kanbanStep) {
              kanbanStep.textContent = step;
            }
          });
        });
      }

      const forms = createBoard.querySelectorAll(selectors.FORMS);
      forms.forEach((form, index) => {
        form.addEventListener(events.SUBMIT, e => {
          e.preventDefault();
          const formData = new FormData(e.target);
          Object.fromEntries(formData.entries());
          if (index + 1 === forms.length) {
            window.location.reload();
          }
          return null;
        });
      });
      // custom color
      const colorPicker = document.querySelector('#customColorInput');
      colorPicker?.addEventListener(events.CHANGE, event => {
        const selectedColor = event.target.value;
        const customColorRadioBtn = document.querySelector(
          selectors.CUSTOM_COLOR
        );
        customColorRadioBtn.setAttribute('checked', 'checked');
        customColorRadioBtn.value = selectedColor;
      });
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                                  Detector                                  */
  /* -------------------------------------------------------------------------- */

  const detectorInit = () => {
    const { addClass } = window.phoenix.utils;
    const { is } = window;
    const html = document.querySelector('html');

    is.opera() && addClass(html, 'opera');
    is.mobile() && addClass(html, 'mobile');
    is.firefox() && addClass(html, 'firefox');
    is.safari() && addClass(html, 'safari');
    is.ios() && addClass(html, 'ios');
    is.iphone() && addClass(html, 'iphone');
    is.ipad() && addClass(html, 'ipad');
    is.ie() && addClass(html, 'ie');
    is.edge() && addClass(html, 'edge');
    is.chrome() && addClass(html, 'chrome');
    is.mac() && addClass(html, 'osx');
    is.windows() && addClass(html, 'windows');
    navigator.userAgent.match('CriOS') && addClass(html, 'chrome');
  };

  /* -------------------------------------------------------------------------- */
  /*                           Open dropdown on hover                           */
  /* -------------------------------------------------------------------------- */

  const dropdownOnHover = () => {
    const navbarArea = document.querySelector('[data-dropdown-on-hover]');

    if (navbarArea) {
      navbarArea.addEventListener('mouseover', e => {
        if (
          e.target?.classList.contains('dropdown-toggle') &&
          !e.target.parentNode.className.includes('dropdown-inside') &&
          window.innerWidth > 992
        ) {
          const dropdownInstance = new window.bootstrap.Dropdown(e.target);

          /* eslint-disable no-underscore-dangle */
          dropdownInstance._element.classList.add('show');
          dropdownInstance._menu.classList.add('show');
          dropdownInstance._menu.setAttribute('data-bs-popper', 'none');

          e.target.parentNode.addEventListener('mouseleave', () => {
            if (window.innerWidth > 992) {
              dropdownInstance.hide();
            }
          });
        }
      });
    }
  };

  /* eslint-disable */
  const { merge: merge$1 } = window._;

  /*-----------------------------------------------
  |   Dropzone
  -----------------------------------------------*/

  window.Dropzone ? (window.Dropzone.autoDiscover = false) : '';

  const dropzoneInit = () => {
    const { getData } = window.phoenix.utils;
    const Selector = {
      DROPZONE: '[data-dropzone]',
      DZ_ERROR_MESSAGE: '.dz-error-message',
      DZ_PREVIEW: '.dz-preview',
      DZ_PROGRESS: '.dz-preview .dz-preview-cover .dz-progress',
      DZ_PREVIEW_COVER: '.dz-preview .dz-preview-cover'
    };

    const ClassName = {
      DZ_FILE_PROCESSING: 'dz-file-processing',
      DZ_FILE_COMPLETE: 'dz-file-complete',
      DZ_COMPLETE: 'dz-complete',
      DZ_PROCESSING: 'dz-processing'
    };

    const DATA_KEY = {
      OPTIONS: 'options'
    };

    const Events = {
      ADDED_FILE: 'addedfile',
      REMOVED_FILE: 'removedfile',
      COMPLETE: 'complete'
    };

    const dropzones = document.querySelectorAll(Selector.DROPZONE);

    !!dropzones.length &&
      dropzones.forEach(item => {
        let userOptions = getData(item, DATA_KEY.OPTIONS);
        userOptions = userOptions ? userOptions : {};
        const data = userOptions.data ? userOptions.data : {};
        const options = merge$1(
          {
            url: '/assets/php/',
            addRemoveLinks: false,
            previewsContainer: item.querySelector(Selector.DZ_PREVIEW),
            previewTemplate: item.querySelector(Selector.DZ_PREVIEW).innerHTML,
            thumbnailWidth: null,
            thumbnailHeight: null,
            maxFilesize: 2,
            autoProcessQueue: false,
            filesizeBase: 1000,
            init: function init() {
              const thisDropzone = this;

              if (data.length) {
                data.forEach(v => {
                  const mockFile = { name: v.name, size: v.size };
                  thisDropzone.options.addedfile.call(thisDropzone, mockFile);
                  thisDropzone.options.thumbnail.call(
                    thisDropzone,
                    mockFile,
                    `${v.url}/${v.name}`
                  );
                });
              }

              thisDropzone.on(Events.ADDED_FILE, function addedfile() {
                if ('maxFiles' in userOptions) {
                  if (
                    userOptions.maxFiles === 1 &&
                    item.querySelectorAll(Selector.DZ_PREVIEW_COVER).length > 1
                  ) {
                    item.querySelector(Selector.DZ_PREVIEW_COVER).remove();
                  }
                  if (userOptions.maxFiles === 1 && this.files.length > 1) {
                    this.removeFile(this.files[0]);
                  }
                }
              });
            },
            error(file, message) {
              if (file.previewElement) {
                file.previewElement.classList.add('dz-error');
                if (typeof message !== 'string' && message.error) {
                  message = message.error;
                }
                for (let node of file.previewElement.querySelectorAll(
                  '[data-dz-errormessage]'
                )) {
                  node.textContent = message;
                }
              }
            }
          },
          userOptions
        );
        // eslint-disable-next-line
        item.querySelector(Selector.DZ_PREVIEW).innerHTML = '';

        const dropzone = new window.Dropzone(item, options);

        dropzone.on(Events.ADDED_FILE, () => {
          if (item.querySelector(Selector.DZ_PREVIEW_COVER)) {
            item
              .querySelector(Selector.DZ_PREVIEW_COVER)
              .classList.remove(ClassName.DZ_FILE_COMPLETE);
          }
          item.classList.add(ClassName.DZ_FILE_PROCESSING);
          // Kanban custom bg radio select
          document
            .querySelector('.kanban-custom-bg-radio')
            .setAttribute('checked', true);
        });
        dropzone.on(Events.REMOVED_FILE, () => {
          if (item.querySelector(Selector.DZ_PREVIEW_COVER)) {
            item
              .querySelector(Selector.DZ_PREVIEW_COVER)
              .classList.remove(ClassName.DZ_PROCESSING);
          }
          item.classList.add(ClassName.DZ_FILE_COMPLETE);
        });
        dropzone.on(Events.COMPLETE, () => {
          if (item.querySelector(Selector.DZ_PREVIEW_COVER)) {
            item
              .querySelector(Selector.DZ_PREVIEW_COVER)
              .classList.remove(ClassName.DZ_PROCESSING);
          }

          item.classList.add(ClassName.DZ_FILE_COMPLETE);
        });
      });
  };

  // import feather from 'feather-icons';
  /* -------------------------------------------------------------------------- */
  /*                            Feather Icons                                   */
  /* -------------------------------------------------------------------------- */

  const featherIconsInit = () => {
    if (window.feather) {
      window.feather.replace({
        width: '16px',
        height: '16px'
      });
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                                  Flatpickr                                 */
  /* -------------------------------------------------------------------------- */

  const flatpickrInit = () => {
    const { getData } = window.phoenix.utils;
    document.querySelectorAll('.datetimepicker').forEach(item => {
      const userOptions = getData(item, 'options');
      window.flatpickr(item, {
        nextArrow: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 512"><!--! Font Awesome Pro 6.1.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license (Commercial License) Copyright 2022 Fonticons, Inc. --><path d="M96 480c-8.188 0-16.38-3.125-22.62-9.375c-12.5-12.5-12.5-32.75 0-45.25L242.8 256L73.38 86.63c-12.5-12.5-12.5-32.75 0-45.25s32.75-12.5 45.25 0l192 192c12.5 12.5 12.5 32.75 0 45.25l-192 192C112.4 476.9 104.2 480 96 480z"/></svg>`,
        prevArrow: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 512"><!--! Font Awesome Pro 6.1.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license (Commercial License) Copyright 2022 Fonticons, Inc. --><path d="M224 480c-8.188 0-16.38-3.125-22.62-9.375l-192-192c-12.5-12.5-12.5-32.75 0-45.25l192-192c12.5-12.5 32.75-12.5 45.25 0s12.5 32.75 0 45.25L77.25 256l169.4 169.4c12.5 12.5 12.5 32.75 0 45.25C240.4 476.9 232.2 480 224 480z"/></svg>`,
        locale: {
          firstDayOfWeek: 1,

          shorthand: ['S', 'M', 'T', 'W', 'T', 'F', 'S']
        },
        monthSelectorType: 'static',
        onDayCreate: (dObj, dStr, fp, dayElem) => {
          if (dayElem.dateObj.getDay() === 6 || dayElem.dateObj.getDay() === 0) {
            dayElem.className += ' weekend-days';
          }
        },
        ...userOptions
      });

      // datepicker.l10n.weekdays.shorthand = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
    });
  };

  /* -------------------------------------------------------------------------- */
  /*                              Form Validation                               */
  /* -------------------------------------------------------------------------- */

  const formValidationInit = () => {
    const forms = document.querySelectorAll('.needs-validation');

    forms.forEach(form => {
      form.addEventListener(
        'submit',
        event => {
          if (!form.checkValidity()) {
            event.preventDefault();
            event.stopPropagation();
          }
          form.classList.add('was-validated');
        },
        false
      );
    });
  };

  /* -------------------------------------------------------------------------- */
  /*                                   Calendar                                 */

  /* -------------------------------------------------------------------------- */
  const renderCalendar = (el, option) => {
    const { merge } = window._;

    const options = merge(
      {
        initialView: 'dayGridMonth',
        weekNumberCalculation: 'ISO',
        editable: true,
        direction: document.querySelector('html').getAttribute('dir'),
        headerToolbar: {
          left: 'prev,next today',
          center: 'title',
          right: 'dayGridMonth,timeGridWeek,timeGridDay'
        },
        buttonText: {
          month: 'Month',
          week: 'Week',
          day: 'Day'
        }
      },
      option
    );
    const calendar = new window.FullCalendar.Calendar(el, options);
    calendar.render();
    document
      .querySelector('.navbar-vertical-toggle')
      ?.addEventListener('navbar.vertical.toggle', () => calendar.updateSize());
    return calendar;
  };

  const fullCalendarInit = () => {
    const { getData } = window.phoenix.utils;

    const calendars = document.querySelectorAll('[data-calendar]');
    calendars.forEach(item => {
      const options = getData(item, 'calendar');
      renderCalendar(item, options);
    });
  };

  /* -------------------------------------------------------------------------- */
  /*                                 Glightbox                                */
  /* -------------------------------------------------------------------------- */

  const glightboxInit = () => {
    if (window.GLightbox) {
      window.GLightbox({
        selector: '[data-gallery]'
      });
    }
  };

  /*-----------------------------------------------
  |   Gooogle Map
  -----------------------------------------------*/

  function initMap() {
    const { getData } = window.phoenix.utils;
    const themeController = document.body;
    const $googlemaps = document.querySelectorAll('[data-googlemap]');
    if ($googlemaps.length && window.google) {
      const createControlBtn = (map, type) => {
        const controlButton = document.createElement('button');
        controlButton.classList.add(type);
        controlButton.innerHTML =
          type === 'zoomIn'
            ? '<span class="fas fa-plus text-body-emphasis"></span>'
            : '<span class="fas fa-minus text-body-emphasis"></span>';

        controlButton.addEventListener('click', () => {
          const zoom = map.getZoom();
          if (type === 'zoomIn') {
            map.setZoom(zoom + 1);
          }
          if (type === 'zoomOut') {
            map.setZoom(zoom - 1);
          }
        });

        return controlButton;
      };
      const mapStyles = {
        SnazzyCustomLight: [
          {
            featureType: 'administrative',
            elementType: 'all',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'administrative',
            elementType: 'labels',
            stylers: [
              {
                visibility: 'on'
              }
            ]
          },
          {
            featureType: 'administrative',
            elementType: 'labels.text.fill',
            stylers: [
              {
                color: '#525b75'
              }
            ]
          },
          {
            featureType: 'administrative',
            elementType: 'labels.text.stroke',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'administrative',
            elementType: 'labels.icon',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'administrative.country',
            elementType: 'geometry.stroke',
            stylers: [
              {
                visibility: 'on'
              },
              {
                color: '#ffffff'
              }
            ]
          },
          {
            featureType: 'administrative.province',
            elementType: 'geometry.stroke',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'landscape',
            elementType: 'geometry',
            stylers: [
              {
                visibility: 'on'
              },
              {
                color: '#E3E6ED'
              }
            ]
          },
          {
            featureType: 'landscape.natural',
            elementType: 'labels',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'poi',
            elementType: 'all',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'road',
            elementType: 'all',
            stylers: [
              {
                color: '#eff2f6'
              }
            ]
          },
          {
            featureType: 'road',
            elementType: 'labels',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'road.arterial',
            elementType: 'all',
            stylers: [
              {
                visibility: 'on'
              }
            ]
          },
          {
            featureType: 'road.arterial',
            elementType: 'geometry',
            stylers: [
              {
                visibility: 'on'
              },
              {
                color: '#eff2f6'
              }
            ]
          },
          {
            featureType: 'road.arterial',
            elementType: 'labels.text.fill',
            stylers: [
              {
                visibility: 'on'
              },
              {
                color: '#9fa6bc'
              }
            ]
          },
          {
            featureType: 'road.arterial',
            elementType: 'labels.text.stroke',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'road.local',
            elementType: 'geometry.fill',
            stylers: [
              {
                visibility: 'on'
              },
              {
                color: '#eff2f6'
              }
            ]
          },
          {
            featureType: 'road.local',
            elementType: 'labels.text.fill',
            stylers: [
              {
                visibility: 'on'
              },
              {
                color: '#9fa6bc'
              }
            ]
          },
          {
            featureType: 'road.local',
            elementType: 'labels.text.stroke',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'transit',
            elementType: 'labels.icon',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'transit.line',
            elementType: 'geometry',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'transit.line',
            elementType: 'labels.text',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'transit.station.airport',
            elementType: 'geometry',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'transit.station.airport',
            elementType: 'labels',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'water',
            elementType: 'geometry',
            stylers: [
              {
                color: '#F5F7FA'
              }
            ]
          },
          {
            featureType: 'water',
            elementType: 'labels',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          }
        ],
        SnazzyCustomDark: [
          {
            featureType: 'administrative',
            elementType: 'all',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'administrative',
            elementType: 'labels',
            stylers: [{ visibility: 'on' }]
          },
          {
            featureType: 'administrative',
            elementType: 'labels.text.fill',
            stylers: [
              {
                color: '#8a94ad'
              }
            ]
          },
          {
            featureType: 'administrative',
            elementType: 'labels.text.stroke',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'administrative',
            elementType: 'labels.icon',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'administrative.country',
            elementType: 'geometry.stroke',
            stylers: [
              { visibility: 'on' },
              {
                color: '#000000'
              }
            ]
          },
          {
            featureType: 'administrative.province',
            elementType: 'geometry.stroke',
            stylers: [{ visibility: 'off' }]
          },
          {
            featureType: 'landscape',
            elementType: 'geometry',
            stylers: [{ visibility: 'on' }, { color: '#222834' }]
          },
          {
            featureType: 'landscape.natural',
            elementType: 'labels',
            stylers: [{ visibility: 'off' }]
          },
          {
            featureType: 'poi',
            elementType: 'all',
            stylers: [{ visibility: 'off' }]
          },
          {
            featureType: 'road',
            elementType: 'all',
            stylers: [{ color: '#141824' }]
          },
          {
            featureType: 'road',
            elementType: 'labels',
            stylers: [{ visibility: 'off' }]
          },
          {
            featureType: 'road.arterial',
            elementType: 'all',
            stylers: [
              {
                visibility: 'on'
              }
            ]
          },
          {
            featureType: 'road.arterial',
            elementType: 'geometry',
            stylers: [
              {
                visibility: 'on'
              },
              {
                color: '#141824'
              }
            ]
          },
          {
            featureType: 'road.arterial',
            elementType: 'labels.text.fill',
            stylers: [
              {
                visibility: 'on'
              },
              {
                color: '#525b75'
              }
            ]
          },
          {
            featureType: 'road.arterial',
            elementType: 'labels.text.stroke',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'road.local',
            elementType: 'geometry.fill',
            stylers: [
              {
                visibility: 'on'
              },
              {
                color: '#141824'
              }
            ]
          },
          {
            featureType: 'road.local',
            elementType: 'labels.text.fill',
            stylers: [
              {
                visibility: 'on'
              },
              {
                color: '#67718A'
              }
            ]
          },
          {
            featureType: 'road.local',
            elementType: 'labels.text.stroke',
            stylers: [
              {
                visibility: 'off'
              }
            ]
          },
          {
            featureType: 'transit',
            elementType: 'labels.icon',
            stylers: [{ visibility: 'off' }]
          },
          {
            featureType: 'transit.line',
            elementType: 'geometry',
            stylers: [{ visibility: 'off' }]
          },
          {
            featureType: 'transit.line',
            elementType: 'labels.text',
            stylers: [{ visibility: 'off' }]
          },
          {
            featureType: 'transit.station.airport',
            elementType: 'geometry',
            stylers: [{ visibility: 'off' }]
          },
          {
            featureType: 'transit.station.airport',
            elementType: 'labels',
            stylers: [{ visibility: 'off' }]
          },
          {
            featureType: 'water',
            elementType: 'geometry',
            stylers: [{ color: '#0f111a' }]
          },
          {
            featureType: 'water',
            elementType: 'labels',
            stylers: [{ visibility: 'off' }]
          }
        ]
      };

      $googlemaps.forEach(itm => {
        const latLng = getData(itm, 'latlng').split(',');
        const markerPopup = itm.innerHTML;
        const zoom = getData(itm, 'zoom');
        const mapElement = itm;
        const mapStyle = getData(itm, 'phoenixTheme');

        if (getData(itm, 'phoenixTheme') === 'streetview') {
          const pov = getData(itm, 'pov');
          const mapOptions = {
            position: { lat: Number(latLng[0]), lng: Number(latLng[1]) },
            pov,
            zoom,
            gestureHandling: 'none',
            scrollwheel: false
          };

          return new window.google.maps.StreetViewPanorama(
            mapElement,
            mapOptions
          );
        }

        const mapOptions = {
          zoom,
          minZoom: 1.2,
          clickableIcons: false,
          zoomControl: false,
          zoomControlOptions: {
            position: window.google.maps.ControlPosition.LEFT
          },
          scrollwheel: getData(itm, 'scrollwheel'),
          disableDefaultUI: true,
          center: new window.google.maps.LatLng(latLng[0], latLng[1]),
          styles:
            window.config.config.phoenixTheme === 'dark'
              ? mapStyles.SnazzyCustomDark
              : mapStyles[mapStyle || 'SnazzyCustomLight']
        };

        const map = new window.google.maps.Map(mapElement, mapOptions);
        const infoWindow = new window.google.maps.InfoWindow({
          content: markerPopup
        });

        // Create the DIV to hold the control.
        const controlDiv = document.createElement('div');
        controlDiv.classList.add('google-map-control-btn');
        // Create the control.
        const zoomInBtn = createControlBtn(map, 'zoomIn');
        const zoomOutBtn = createControlBtn(map, 'zoomOut');
        // Append the control to the DIV.
        controlDiv.appendChild(zoomInBtn);
        controlDiv.appendChild(zoomOutBtn);

        map.controls[window.google.maps.ControlPosition.LEFT].push(controlDiv);

        const marker = new window.google.maps.Marker({
          position: new window.google.maps.LatLng(latLng[0], latLng[1]),
          // icon,
          map
        });

        marker.addListener('click', () => {
          infoWindow.open(map, marker);
        });

        themeController &&
          themeController.addEventListener(
            'clickControl',
            ({ detail: { control, value } }) => {
              if (control === 'phoenixTheme') {
                map.set(
                  'styles',
                  value === 'dark'
                    ? mapStyles.SnazzyCustomDark
                    : mapStyles.SnazzyCustomLight
                );
              }
            }
          );

        // return null;
      });
    }
  }

  /* -------------------------------------------------------------------------- */
  /*                           Icon copy to clipboard                           */
  /* -------------------------------------------------------------------------- */

  const iconCopiedInit = () => {
    const iconList = document.getElementById('icon-list');
    const iconCopiedToast = document.getElementById('icon-copied-toast');
    const iconCopiedToastInstance = new window.bootstrap.Toast(iconCopiedToast);

    if (iconList) {
      iconList.addEventListener('click', e => {
        const el = e.target;
        if (el.tagName === 'INPUT') {
          el.select();
          el.setSelectionRange(0, 99999);
          document.execCommand('copy');
          iconCopiedToast.querySelector(
            '.toast-body'
          ).innerHTML = `<span class="fw-black">Copied:</span>  <code>${el.value}</code>`;
          iconCopiedToastInstance.show();
        }
      });
    }
  };

  /*-----------------------------------------------
  |                     Isotope
  -----------------------------------------------*/

  const isotopeInit = () => {
    const { getData } = window.phoenix.utils;
    const Selector = {
      ISOTOPE_ITEM: '.isotope-item',
      DATA_ISOTOPE: '[data-sl-isotope]',
      DATA_FILTER: '[data-filter]',
      DATA_FILER_NAV: '[data-filter-nav]',
      DATA_GALLERY_COLUMN: '[data-gallery-column]'
    };

    const DATA_KEY = {
      ISOTOPE: 'sl-isotope'
    };
    const ClassName = {
      ACTIVE: 'active'
    };

    if (window.Isotope) {
      const masonryItems = document.querySelectorAll(Selector.DATA_ISOTOPE);
      const columnGallery = document.querySelector(Selector.DATA_GALLERY_COLUMN);
      if (masonryItems.length) {
        masonryItems.forEach(masonryItem => {
          window.imagesLoaded(masonryItem, () => {
            document.querySelectorAll(Selector.ISOTOPE_ITEM).forEach(item => {
              // eslint-disable-next-line no-param-reassign
              item.style.visibility = 'visible';
            });

            const userOptions = getData(masonryItem, DATA_KEY.ISOTOPE);
            const defaultOptions = {
              itemSelector: Selector.ISOTOPE_ITEM,
              layoutMode: 'packery'
            };

            const options = window._.merge(defaultOptions, userOptions);
            const isotope = new window.Isotope(masonryItem, options);
            const addSeparator = (count = 4) => {
              for (let i = 1; i < count; i += 1) {
                const separator = document.createElement('span');
                separator.classList.add(
                  `gallery-column-separator`,
                  `gallery-column-separator-${i}`
                );
                masonryItem.appendChild(separator);
              }
            };
            const removeSeparator = () => {
              document
                .querySelectorAll('span[class*="gallery-column-separator-"]')
                .forEach(separatorEle => separatorEle.remove());
            };
            if (columnGallery) addSeparator();
            // --------- filter -----------------
            const filterElement = document.querySelector(Selector.DATA_FILER_NAV);
            filterElement?.addEventListener('click', e => {
              const item = e.target.dataset.filter;
              isotope.arrange({ filter: item });
              document.querySelectorAll(Selector.DATA_FILTER).forEach(el => {
                el.classList.remove(ClassName.ACTIVE);
              });
              e.target.classList.add(ClassName.ACTIVE);
              const filteredItems = isotope.getFilteredItemElements();
              if (columnGallery) {
                removeSeparator();
              }
              setTimeout(() => {
                if (columnGallery) {
                  addSeparator(
                    filteredItems.length > 4 ? 4 : filteredItems.length
                  );
                }
                isotope.layout();
              }, 400);
            });
            // ---------- filter end ------------
            isotope.layout();
            return isotope;
          });
        });
      }
    }
  };

  /* eslint-disable no-unused-expressions */
  /* -------------------------------------------------------------------------- */
  /*                                 Data Table                                 */
  /* -------------------------------------------------------------------------- */
  /* eslint-disable no-param-reassign */
  const togglePaginationButtonDisable = (button, disabled) => {
    button.disabled = disabled;
    button.classList[disabled ? 'add' : 'remove']('disabled');
  };

  const listInit = () => {
    const { getData } = window.phoenix.utils;
    if (window.List) {
      const lists = document.querySelectorAll('[data-list]');

      if (lists.length) {
        lists.forEach(el => {
          const bulkSelect = el.querySelector('[data-bulk-select]');

          let options = getData(el, 'list');

          if (options.pagination) {
            options = {
              ...options,
              pagination: {
                item: `<li><button class='page' type='button'></button></li>`,
                ...options.pagination
              }
            };
          }

          const paginationButtonNext = el.querySelector(
            '[data-list-pagination="next"]'
          );
          const paginationButtonPrev = el.querySelector(
            '[data-list-pagination="prev"]'
          );
          const viewAll = el.querySelector('[data-list-view="*"]');
          const viewLess = el.querySelector('[data-list-view="less"]');
          const listInfo = el.querySelector('[data-list-info]');
          const listFilter = el.querySelector('[data-list-filter]');
          const list = new List(el, options);

          // ---------------------------------------

          let totalItem = list.items.length;
          const itemsPerPage = list.page;
          const btnDropdownClose = list.listContainer.querySelector('.btn-close');
          let pageQuantity = Math.ceil(list.size() / list.page);
          let pageCount = 1;
          let numberOfcurrentItems =
            (pageCount - 1) * Number(list.page) + list.visibleItems.length;
          let isSearching = false;

          btnDropdownClose &&
            btnDropdownClose.addEventListener('search.close', () => {
              list.fuzzySearch('');
            });

          const updateListControls = () => {
            listInfo &&
              (listInfo.innerHTML = `${list.i} to ${numberOfcurrentItems} <span class='text-body-tertiary'> Items of </span>${totalItem}`);

            paginationButtonPrev &&
              togglePaginationButtonDisable(
                paginationButtonPrev,
                pageCount === 1 || pageCount === 0
              );
            paginationButtonNext &&
              togglePaginationButtonDisable(
                paginationButtonNext,
                pageCount === pageQuantity || pageCount === 0
              );

            if (pageCount > 1 && pageCount < pageQuantity) {
              togglePaginationButtonDisable(paginationButtonNext, false);
              togglePaginationButtonDisable(paginationButtonPrev, false);
            }
          };

          // List info
          updateListControls();

          if (paginationButtonNext) {
            paginationButtonNext.addEventListener('click', e => {
              e.preventDefault();
              pageCount += 1;
              const nextInitialIndex = list.i + itemsPerPage;
              nextInitialIndex <= list.size() &&
                list.show(nextInitialIndex, itemsPerPage);
            });
          }

          if (paginationButtonPrev) {
            paginationButtonPrev.addEventListener('click', e => {
              e.preventDefault();
              pageCount -= 1;
              const prevItem = list.i - itemsPerPage;
              prevItem > 0 && list.show(prevItem, itemsPerPage);
            });
          }

          const toggleViewBtn = () => {
            viewLess.classList.toggle('d-none');
            viewAll.classList.toggle('d-none');
          };

          if (viewAll) {
            viewAll.addEventListener('click', () => {
              list.show(1, totalItem);
              pageCount = 1;
              toggleViewBtn();
            });
          }
          if (viewLess) {
            viewLess.addEventListener('click', () => {
              list.show(1, itemsPerPage);
              pageCount = 1;
              toggleViewBtn();
            });
          }
          // numbering pagination
          if (options.pagination) {
            el.querySelector('.pagination').addEventListener('click', e => {
              if (e.target.classList[0] === 'page') {
                const pageNum = Number(e.target.getAttribute('data-i'));
                if (pageNum) {
                  list.show(itemsPerPage * (pageNum - 1) + 1, list.page);
                  pageCount = pageNum;
                }
              }
            });
          }
          // filter
          if (options.filter) {
            const { key } = options.filter;
            listFilter.addEventListener('change', e => {
              list.filter(item => {
                if (e.target.value === '') {
                  return true;
                }
                pageQuantity = Math.ceil(list.matchingItems.length / list.page);
                pageCount = 1;
                updateListControls();
                return item
                  .values()
                  [key].toLowerCase()
                  .includes(e.target.value.toLowerCase());
              });
            });
          }

          // bulk-select
          if (bulkSelect) {
            const bulkSelectInstance =
              window.phoenix.BulkSelect.getInstance(bulkSelect);
            bulkSelectInstance.attachRowNodes(
              list.items.map(item =>
                item.elm.querySelector('[data-bulk-select-row]')
              )
            );

            bulkSelect.addEventListener('change', () => {
              if (list) {
                if (bulkSelect.checked) {
                  list.items.forEach(item => {
                    item.elm.querySelector(
                      '[data-bulk-select-row]'
                    ).checked = true;
                  });
                } else {
                  list.items.forEach(item => {
                    item.elm.querySelector(
                      '[data-bulk-select-row]'
                    ).checked = false;
                  });
                }
              }
            });
          }

          list.on('searchStart', () => {
            isSearching = true;
          });
          list.on('searchComplete', () => {
            isSearching = false;
          });

          list.on('updated', item => {
            if (!list.matchingItems.length) {
              pageQuantity = Math.ceil(list.size() / list.page);
            } else {
              pageQuantity = Math.ceil(list.matchingItems.length / list.page);
            }
            numberOfcurrentItems =
              (pageCount - 1) * Number(list.page) + list.visibleItems.length;
            updateListControls();

            // -------search-----------
            if (isSearching) {
              if (list.matchingItems.length === 0) {
                pageCount = 0;
              } else {
                pageCount = 1;
              }
              totalItem = list.matchingItems.length;
              numberOfcurrentItems =
                (pageCount === 0 ? 1 : pageCount - 1) * Number(list.page) +
                list.visibleItems.length;

              updateListControls();
              listInfo &&
                (listInfo.innerHTML = `${
                list.matchingItems.length === 0 ? 0 : list.i
              } to ${
                list.matchingItems.length === 0 ? 0 : numberOfcurrentItems
              } <span class='text-body-tertiary'> Items of </span>${
                list.matchingItems.length
              }`);
            }

            // -------fallback-----------
            const fallback =
              el.querySelector('.fallback') ||
              document.getElementById(options.fallback);

            if (fallback) {
              if (item.matchingItems.length === 0) {
                fallback.classList.remove('d-none');
              } else {
                fallback.classList.add('d-none');
              }
            }
          });
        });
      }
    }
  };

  const lottieInit = () => {
    const { getData } = window.phoenix.utils;
    const lotties = document.querySelectorAll('.lottie');
    if (lotties.length) {
      lotties.forEach(item => {
        const options = getData(item, 'options');
        window.bodymovin.loadAnimation({
          container: item,
          path: '../img/animated-icons/warning-light.json',
          renderer: 'svg',
          loop: true,
          autoplay: true,
          name: 'Hello World',
          ...options
        });
      });
    }
  };

  /* ----------------------------------------------------------------- */
  /*                               Modal                               */
  /* ----------------------------------------------------------------- */

  const modalInit = () => {
    const $modals = document.querySelectorAll('[data-phoenix-modal]');

    if ($modals) {
      const { getData, getCookie, setCookie } = window.phoenix.utils;
      $modals.forEach(modal => {
        const userOptions = getData(modal, 'phoenix-modal');
        const defaultOptions = {
          autoShow: false
        };
        const options = window._.merge(defaultOptions, userOptions);
        if (options.autoShow) {
          const autoShowModal = new window.bootstrap.Modal(modal);
          const disableModalBtn = modal.querySelector(
            '[data-disable-modal-auto-show]'
          );

          disableModalBtn.addEventListener('click', () => {
            const seconds = 24 * 60 * 60;
            setCookie('disableAutoShowModal', 'true', seconds);
          });

          const disableAutoShowModalCookie = getCookie('disableAutoShowModal');
          if (!disableAutoShowModalCookie) {
            autoShowModal.show();
          }
        } else {
          modal.addEventListener('shown.bs.modal', () => {
            const $autofocusEls = modal.querySelectorAll('[autofocus=autofocus]');
            $autofocusEls.forEach(el => {
              el.focus();
            });
          });
        }
      });
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                             Navbar Combo Layout                            */
  /* -------------------------------------------------------------------------- */

  const navbarComboInit = () => {
    const { getBreakpoint, getData, addClass, hasClass, resize } =
      window.phoenix.utils;

    const Selector = {
      NAVBAR_VERTICAL: '.navbar-vertical',
      NAVBAR_TOP_COMBO: '[data-navbar-top="combo"]',
      COLLAPSE: '.collapse',
      DATA_MOVE_CONTAINER: '[data-move-container]',
      NAVBAR_NAV: '.navbar-nav',
      NAVBAR_VERTICAL_DIVIDER: '.navbar-vertical-divider'
    };

    const ClassName = {
      FLEX_COLUMN: 'flex-column'
    };

    const navbarVertical = document.querySelector(Selector.NAVBAR_VERTICAL);
    const navbarTopCombo = document.querySelector(Selector.NAVBAR_TOP_COMBO);

    const moveNavContent = windowWidth => {
      const navbarVerticalBreakpoint = getBreakpoint(navbarVertical);
      const navbarTopBreakpoint = getBreakpoint(navbarTopCombo);

      if (windowWidth < navbarTopBreakpoint) {
        const navbarCollapse = navbarTopCombo.querySelector(Selector.COLLAPSE);
        const navbarTopContent = navbarCollapse.innerHTML;

        if (navbarTopContent) {
          const targetID = getData(navbarTopCombo, 'move-target');
          const targetElement = document.querySelector(targetID);

          navbarCollapse.innerHTML = '';
          targetElement.insertAdjacentHTML(
            'afterend',
            `
            <div data-move-container class='move-container'>
              <div class='navbar-vertical-divider'>
                <hr class='navbar-vertical-hr' />
              </div>
              ${navbarTopContent}
            </div>
          `
          );

          if (navbarVerticalBreakpoint < navbarTopBreakpoint) {
            const navbarNav = document
              .querySelector(Selector.DATA_MOVE_CONTAINER)
              .querySelector(Selector.NAVBAR_NAV);
            addClass(navbarNav, ClassName.FLEX_COLUMN);
          }
        }
      } else {
        const moveableContainer = document.querySelector(
          Selector.DATA_MOVE_CONTAINER
        );
        if (moveableContainer) {
          const navbarNav = moveableContainer.querySelector(Selector.NAVBAR_NAV);
          hasClass(navbarNav, ClassName.FLEX_COLUMN) &&
            navbarNav.classList.remove(ClassName.FLEX_COLUMN);
          moveableContainer
            .querySelector(Selector.NAVBAR_VERTICAL_DIVIDER)
            .remove();
          navbarTopCombo.querySelector(Selector.COLLAPSE).innerHTML =
            moveableContainer.innerHTML;
          moveableContainer.remove();
        }
      }
    };

    moveNavContent(window.innerWidth);

    resize(() => moveNavContent(window.innerWidth));
  };

  const navbarShadowOnScrollInit = () => {
    const navbar = document.querySelector('[data-navbar-shadow-on-scroll]');
    if (navbar) {
      window.onscroll = () => {
        if (window.scrollY > 300) {
          navbar.classList.add('navbar-shadow');
        } else {
          navbar.classList.remove('navbar-shadow');
        }
      };
    }
  };

  const navbarInit = () => {
    const navbar = document.querySelector('[data-navbar-soft-on-scroll]');
    if (navbar) {
      const windowHeight = window.innerHeight;
      const handleAlpha = () => {
        const scrollTop = window.pageYOffset;
        let alpha = (scrollTop / windowHeight) * 2;
        alpha >= 1 && (alpha = 1);
        navbar.style.backgroundColor = `rgba(255, 255, 255, ${alpha})`;
      };
      handleAlpha();
      document.addEventListener('scroll', () => handleAlpha());
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                               Navbar Vertical                              */
  /* -------------------------------------------------------------------------- */

  const handleNavbarVerticalCollapsed = () => {
    const { getItemFromStore, setItemToStore, resize } = window.phoenix.utils;
    const Selector = {
      HTML: 'html',
      BODY: 'body',
      NAVBAR_VERTICAL: '.navbar-vertical',
      NAVBAR_VERTICAL_TOGGLE: '.navbar-vertical-toggle',
      NAVBAR_VERTICAL_COLLAPSE: '.navbar-vertical .navbar-collapse',
      ACTIVE_NAV_LINK: '.navbar-vertical .nav-link.active'
    };

    const Events = {
      CLICK: 'click',
      MOUSE_OVER: 'mouseover',
      MOUSE_LEAVE: 'mouseleave',
      NAVBAR_VERTICAL_TOGGLE: 'navbar.vertical.toggle'
    };
    const ClassNames = {
      NAVBAR_VERTICAL_COLLAPSED: 'navbar-vertical-collapsed'
    };
    const navbarVerticalToggle = document.querySelector(
      Selector.NAVBAR_VERTICAL_TOGGLE
    );
    // const html = document.querySelector(Selector.HTML);
    const navbarVerticalCollapse = document.querySelector(
      Selector.NAVBAR_VERTICAL_COLLAPSE
    );
    const activeNavLinkItem = document.querySelector(Selector.ACTIVE_NAV_LINK);
    if (navbarVerticalToggle) {
      navbarVerticalToggle.addEventListener(Events.CLICK, e => {
        const isNavbarVerticalCollapsed = getItemFromStore(
          'phoenixIsNavbarVerticalCollapsed',
          false
        );
        navbarVerticalToggle.blur();
        document.documentElement.classList.toggle(
          ClassNames.NAVBAR_VERTICAL_COLLAPSED
        );

        // Set collapse state on localStorage
        setItemToStore(
          'phoenixIsNavbarVerticalCollapsed',
          !isNavbarVerticalCollapsed
        );

        const event = new CustomEvent(Events.NAVBAR_VERTICAL_TOGGLE);
        e.currentTarget?.dispatchEvent(event);
      });
    }
    if (navbarVerticalCollapse) {
      const isNavbarVerticalCollapsed = getItemFromStore(
        'phoenixIsNavbarVerticalCollapsed',
        false
      );
      if (activeNavLinkItem && !isNavbarVerticalCollapsed) {
        activeNavLinkItem.scrollIntoView({ behavior: 'smooth' });
      }
    }
    const setDocumentMinHeight = () => {
      const bodyHeight = document.querySelector(Selector.BODY).offsetHeight;
      const navbarVerticalHeight = document.querySelector(
        Selector.NAVBAR_VERTICAL
      )?.offsetHeight;

      if (
        document.documentElement.classList.contains(
          ClassNames.NAVBAR_VERTICAL_COLLAPSED
        ) &&
        bodyHeight < navbarVerticalHeight
      ) {
        document.documentElement.style.minHeight = `${navbarVerticalHeight}px`;
      } else {
        document.documentElement.removeAttribute('style');
      }
    };

    // set document min height for collapse vertical nav
    setDocumentMinHeight();
    resize(() => {
      setDocumentMinHeight();
    });
    if (navbarVerticalToggle) {
      navbarVerticalToggle.addEventListener('navbar.vertical.toggle', () => {
        setDocumentMinHeight();
      });
    }
  };

  /* eslint-disable no-new */
  /*-----------------------------------------------
  |                    Phoenix Offcanvas
  -----------------------------------------------*/

  const phoenixOffcanvasInit = () => {
    const { getData } = window.phoenix.utils;
    const toggleEls = document.querySelectorAll(
      "[data-phoenix-toggle='offcanvas']"
    );
    const offcanvasBackdrop = document.querySelector('[data-phoenix-backdrop]');
    const offcanvasBodyScroll = document.querySelector('[data-phoenix-scroll]');
    const offcanvasFaq = document.querySelector('.faq');
    const offcanvasFaqShow = document.querySelector('.faq-sidebar');

    const showFilterCol = offcanvasEl => {
      offcanvasEl.classList.add('show');
      if (!offcanvasBodyScroll) {
        document.body.style.overflow = 'hidden';
      }
    };
    const hideFilterCol = offcanvasEl => {
      offcanvasEl.classList.remove('show');
      document.body.style.removeProperty('overflow');
    };

    if (toggleEls) {
      toggleEls.forEach(toggleEl => {
        const offcanvasTarget = getData(toggleEl, 'phoenix-target');
        const offcanvasTargetEl = document.querySelector(offcanvasTarget);
        const closeBtn = offcanvasTargetEl.querySelectorAll(
          "[data-phoenix-dismiss='offcanvas']"
        );
        toggleEl.addEventListener('click', () => {
          showFilterCol(offcanvasTargetEl);
        });
        if (closeBtn) {
          closeBtn.forEach(el => {
            el.addEventListener('click', () => {
              hideFilterCol(offcanvasTargetEl);
            });
          });
        }
        if (offcanvasBackdrop) {
          offcanvasBackdrop.addEventListener('click', () => {
            hideFilterCol(offcanvasTargetEl);
          });
        }
      });
    }

    if (offcanvasFaq) {
      if (offcanvasFaqShow.classList.contains('show')) {
        offcanvasFaq.classList.add = 'newFaq';
      }
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                                   Popover                                  */
  /* -------------------------------------------------------------------------- */

  const picmoInit = () => {
    const { getData } = window.phoenix.utils;

    const picmoBtns = document.querySelectorAll('[data-picmo]');

    if (picmoBtns) {
      Array.from(picmoBtns).forEach(btn => {
        const options = getData(btn, 'picmo');

        const picker = window.picmoPopup.createPopup(
          {},
          {
            referenceElement: btn,
            triggerElement: btn,
            position: 'bottom-start',
            showCloseButton: false
          }
        );
        btn.addEventListener('click', () => {
          picker.toggle();
        });

        const input = document.querySelector(options.inputTarget);

        picker.addEventListener('emoji:select', selection => {
          if (input) {
            input.innerHTML += selection.emoji;
          }
        });
      });
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                                   Popover                                  */
  /* -------------------------------------------------------------------------- */

  const popoverInit = () => {
    const popoverTriggerList = Array.from(
      document.querySelectorAll('[data-bs-toggle="popover"]')
    );

    popoverTriggerList.map(popoverTriggerEl => {
      return new bootstrap.Popover(popoverTriggerEl);
    });
  };

  /* eslint-disable no-new */
  /*-----------------------------------------------
  |                    Swiper
  -----------------------------------------------*/

  const getThubmnailDirection = () => {
    if (
      window.innerWidth < 768 ||
      (window.innerWidth >= 992 && window.innerWidth < 1200)
    ) {
      return 'horizontal';
    }
    return 'vertical';
  };

  const productDetailsInit = () => {
    const { getData, resize } = window.phoenix.utils;
    const productDetailsEl = document.querySelector('[data-product-details]');
    if (productDetailsEl) {
      const colorVariantEl = productDetailsEl.querySelector(
        '[data-product-color]'
      );
      productDetailsEl.querySelector(
        '[data-product-quantity]'
      );
      const productQuantityInputEl = productDetailsEl.querySelector(
        '[data-quantity] input[type="number"]'
      );
      const productColorVariantConatiner = productDetailsEl.querySelector(
        '[data-product-color-variants]'
      );

      const swiperInit = productImages => {
        const productSwiper = productDetailsEl.querySelector(
          '[data-products-swiper]'
        );

        const options = getData(productSwiper, 'swiper');

        const thumbTarget = getData(productSwiper, 'thumb-target');

        const thumbEl = document.getElementById(thumbTarget);

        let slides = '';
        productImages.forEach(img => {
          slides += `
          <div class='swiper-slide '>
            <img class='w-100' src=${img} alt="">
          </div>
        `;
        });
        productSwiper.innerHTML = `<div class='swiper-wrapper'>${slides}</div>`;

        let thumbSlides = '';
        productImages.forEach(img => {
          thumbSlides += `
          <div class='swiper-slide '>
            <div class="product-thumb-container p-2 p-sm-3 p-xl-2">
              <img src=${img} alt="">
            </div>
          </div>
        `;
        });
        thumbEl.innerHTML = `<div class='swiper-wrapper'>${thumbSlides}</div>`;

        const thumbSwiper = new window.Swiper(thumbEl, {
          slidesPerView: 5,
          spaceBetween: 16,
          direction: getThubmnailDirection(),
          breakpoints: {
            768: {
              spaceBetween: 100
            },
            992: {
              spaceBetween: 16
            }
          }
        });

        const swiperNav = productSwiper.querySelector('.swiper-nav');

        resize(() => {
          thumbSwiper.changeDirection(getThubmnailDirection());
        });

        new Swiper(productSwiper, {
          ...options,
          navigation: {
            nextEl: swiperNav?.querySelector('.swiper-button-next'),
            prevEl: swiperNav?.querySelector('.swiper-button-prev')
          },
          thumbs: {
            swiper: thumbSwiper
          }
        });
      };

      const colorVariants =
        productColorVariantConatiner.querySelectorAll('[data-variant]');

      colorVariants.forEach(variant => {
        if (variant.classList.contains('active')) {
          swiperInit(getData(variant, 'products-images'));
          colorVariantEl.innerHTML = getData(variant, 'variant');
        }
        const productImages = getData(variant, 'products-images');

        variant.addEventListener('click', () => {
          swiperInit(productImages);
          colorVariants.forEach(colorVariant => {
            colorVariant.classList.remove('active');
          });
          variant.classList.add('active');
          colorVariantEl.innerHTML = getData(variant, 'variant');
        });
      });
      productQuantityInputEl.addEventListener('change', e => {
        if (e.target.value == '') {
          e.target.value = 0;
        }
      });
    }
  };

  /*-----------------------------------------------
  |  Quantity
  -----------------------------------------------*/
  const quantityInit = () => {
    const { getData } = window.phoenix.utils;
    const Selector = {
      DATA_QUANTITY_BTN: '[data-quantity] [data-type]',
      DATA_QUANTITY: '[data-quantity]',
      DATA_QUANTITY_INPUT: '[data-quantity] input[type="number"]'
    };

    const Events = {
      CLICK: 'click'
    };

    const Attributes = {
      MIN: 'min'
    };

    const DataKey = {
      TYPE: 'type'
    };

    const quantities = document.querySelectorAll(Selector.DATA_QUANTITY_BTN);

    quantities.forEach(quantity => {
      quantity.addEventListener(Events.CLICK, e => {
        const el = e.currentTarget;
        const type = getData(el, DataKey.TYPE);
        const numberInput = el
          .closest(Selector.DATA_QUANTITY)
          .querySelector(Selector.DATA_QUANTITY_INPUT);

        const min = numberInput.getAttribute(Attributes.MIN);
        let value = parseInt(numberInput.value, 10);

        if (type === 'plus') {
          value += 1;
        } else {
          value = value > min ? (value -= 1) : value;
        }
        numberInput.value = value;
      });
    });
  };

  /* -------------------------------------------------------------------------- */
  /*                               Ratings                               */
  /* -------------------------------------------------------------------------- */

  const randomColorInit = () => {
    const { getData } = window.phoenix.utils;

    const randomColorElements = document.querySelectorAll('[data-random-color]');
    const defaultColors = [
      '#85A9FF',
      '#60C6FF',
      '#90D67F',
      '#F48270',
      '#3874FF',
      '#0097EB',
      '#25B003',
      '#EC1F00',
      '#E5780B',
      '#004DFF',
      '#0080C7',
      '#23890B',
      '#CC1B00',
      '#D6700A',
      '#222834',
      '#3E465B',
      '#6E7891',
      '#9FA6BC'
    ];

    randomColorElements.forEach(el => {
      const userColors = getData(el, 'random-color');
      let colors;
      if (Array.isArray(userColors)) {
        colors = [...defaultColors, ...userColors];
      } else {
        colors = [...defaultColors];
      }

      el.addEventListener('click', e => {
        const randomColor =
          colors[Math.floor(Math.random() * (colors.length - 1))];
        e.target.value = randomColor;
        const inputLabel = e.target.nextElementSibling;
        // e.target.nextElementSibling.style.boxShadow = `0 0 0 0.2rem ${randomColor}`;
        inputLabel.style.background = `${randomColor}`;
        inputLabel.style.borderColor = `${randomColor}`;
        inputLabel.style.color = `white`;
      });
    });
  };

  /* -------------------------------------------------------------------------- */
  /*                               Ratings                               */
  /* -------------------------------------------------------------------------- */

  const ratingInit = () => {
    const { getData, getItemFromStore } = window.phoenix.utils;
    const raters = document.querySelectorAll('[data-rater]');

    raters.forEach(rater => {
      const options = {
        reverse: getItemFromStore('phoenixIsRTL'),
        starSize: 32,
        step: 0.5,
        element: rater,
        rateCallback(rating, done) {
          this.setRating(rating);
          done();
        },
        ...getData(rater, 'rater')
      };

      return window.raterJs(options);
    });
  };

  /*eslint-disable*/
  /*-----------------------------------------------
  |   Top navigation opacity on scroll
  -----------------------------------------------*/

  const responsiveNavItemsInit = () => {
    const { resize } = window.phoenix.utils;
    const Selector = {
      NAV_ITEM: '[data-nav-item]',
      NAVBAR: '[data-navbar]',
      DROPDOWN: '[data-more-item]',
      CATEGORY_LIST: '[data-category-list]',
      CATEGORY_BUTTON: '[data-category-btn]'
    };

    const navbarEl = document.querySelector(Selector.NAVBAR);

    const navbar = () => {
      const navbarWidth = navbarEl.clientWidth;
      const dropdown = navbarEl.querySelector(Selector.DROPDOWN);
      const dropdownWidth = dropdown.clientWidth;
      const navbarContainerWidth = navbarWidth - dropdownWidth;
      const elements = navbarEl.querySelectorAll(Selector.NAV_ITEM);
      const categoryBtn = navbarEl.querySelector(Selector.CATEGORY_BUTTON);
      const categoryBtnWidth = categoryBtn.clientWidth;

      let totalItemsWidth = 0;
      dropdown.style.display = 'none';

      elements.forEach(item => {
        const itemWidth = item.clientWidth;

        totalItemsWidth = totalItemsWidth + itemWidth;

        if (
          totalItemsWidth + categoryBtnWidth + dropdownWidth >
            navbarContainerWidth &&
          !item.classList.contains('dropdown')
        ) {
          dropdown.style.display = 'block';
          item.style.display = 'none';
          const link = item.firstChild;
          const linkItem = link.cloneNode(true);

          navbarEl.querySelector('.category-list').appendChild(linkItem);
        }
      });
      const dropdownMenu = navbarEl.querySelectorAll('.dropdown-menu .nav-link');

      dropdownMenu.forEach(item => {
        item.classList.remove('nav-link');
        item.classList.add('dropdown-item');
      });
    };

    if (navbarEl) {
      window.addEventListener('load', () => {
        navbar();
        // hideDropdown();
      });

      resize(() => {
        const navElements = navbarEl.querySelectorAll(Selector.NAV_ITEM);
        const dropElements = navbarEl.querySelectorAll(Selector.CATEGORY_LIST);

        navElements.forEach(item => item.removeAttribute('style'));
        dropElements.forEach(item => (item.innerHTML = ''));
        navbar();
        // hideDropdown();
      });

      const navbarLinks = navbarEl.querySelectorAll('.nav-link');

      navbarEl.addEventListener('click', function (e) {
        for (let x = 0; x < navbarLinks.length; x++) {
          navbarLinks[x].classList.remove('active');
        }
        if (e.target.closest('li')) {
          e.target.closest('li').classList.add('active');
        }
      });
    }
  };

  const searchInit = () => {
    const Selectors = {
      SEARCH_DISMISS: '[data-bs-dismiss="search"]',
      DROPDOWN_TOGGLE: '[data-bs-toggle="dropdown"]',
      DROPDOWN_MENU: '.dropdown-menu',
      SEARCH_BOX: '.search-box',
      SEARCH_INPUT: '.search-input',
      SEARCH_TOGGLE: '[data-bs-toggle="search"]'
    };

    const ClassName = {
      SHOW: 'show'
    };

    const Attribute = {
      ARIA_EXPANDED: 'aria-expanded'
    };

    const Events = {
      CLICK: 'click',
      FOCUS: 'focus',
      SHOW_BS_DROPDOWN: 'show.bs.dropdown',
      SEARCH_CLOSE: 'search.close'
    };

    const hideSearchSuggestion = searchArea => {
      const el = searchArea.querySelector(Selectors.SEARCH_TOGGLE);
      const dropdownMenu = searchArea.querySelector(Selectors.DROPDOWN_MENU);
      if (!el || !dropdownMenu) return;

      el.setAttribute(Attribute.ARIA_EXPANDED, 'false');
      el.classList.remove(ClassName.SHOW);
      dropdownMenu.classList.remove(ClassName.SHOW);
    };

    const searchAreas = document.querySelectorAll(Selectors.SEARCH_BOX);

    const hideAllSearchAreas = () => {
      searchAreas.forEach(hideSearchSuggestion);
    };

    searchAreas.forEach(searchArea => {
      const input = searchArea.querySelector(Selectors.SEARCH_INPUT);
      const btnDropdownClose = searchArea.querySelector(Selectors.SEARCH_DISMISS);
      const dropdownMenu = searchArea.querySelector(Selectors.DROPDOWN_MENU);

      if (input) {
        input.addEventListener(Events.FOCUS, () => {
          hideAllSearchAreas();
          const el = searchArea.querySelector(Selectors.SEARCH_TOGGLE);
          if (!el || !dropdownMenu) return;
          el.setAttribute(Attribute.ARIA_EXPANDED, 'true');
          el.classList.add(ClassName.SHOW);
          dropdownMenu.classList.add(ClassName.SHOW);
        });
      }

      document.addEventListener(Events.CLICK, ({ target }) => {
        !searchArea.contains(target) && hideSearchSuggestion(searchArea);
      });

      btnDropdownClose &&
        btnDropdownClose.addEventListener(Events.CLICK, e => {
          hideSearchSuggestion(searchArea);
          input.value = '';
          const event = new CustomEvent(Events.SEARCH_CLOSE);
          e.currentTarget.dispatchEvent(event);
        });
    });

    document.querySelectorAll(Selectors.DROPDOWN_TOGGLE).forEach(dropdown => {
      dropdown.addEventListener(Events.SHOW_BS_DROPDOWN, () => {
        hideAllSearchAreas();
      });
    });
  };

  /* -------------------------------------------------------------------------- */
  /*                                    Toast                                   */
  /* -------------------------------------------------------------------------- */

  const simplebarInit = () => {
    const scrollEl = Array.from(document.querySelectorAll('.scrollbar-overlay'));

    scrollEl.forEach(el => {
      return new window.SimpleBar(el);
    });
  };

  /* -------------------------------------------------------------------------- */
  /*                                 SortableJS                                 */
  /* -------------------------------------------------------------------------- */

  const sortableInit = () => {
    const { getData } = window.phoenix.utils;

    const sortableEl = document.querySelectorAll('[data-sortable]');

    const defaultOptions = {
      animation: 150,
      group: {
        name: 'shared'
      },
      delay: 100,
      delayOnTouchOnly: true, // useful for mobile touch
      forceFallback: true, // * ignore the HTML5 DnD behaviour
      onStart() {
        document.body.classList.add('sortable-dragging'); // to add cursor grabbing
      },
      onEnd() {
        document.body.classList.remove('sortable-dragging');
      }
    };

    sortableEl.forEach(el => {
      const userOptions = getData(el, 'sortable');
      const options = window._.merge(defaultOptions, userOptions);

      return window.Sortable.create(el, options);
    });
  };

  const supportChatInit = () => {
    const supportChat = document.querySelector('.support-chat');
    const supportChatBtn = document.querySelectorAll('.btn-support-chat');
    const supportChatcontainer = document.querySelector(
      '.support-chat-container'
    );
    const { phoenixSupportChat } = window.config.config;

    if (phoenixSupportChat) {
      supportChatcontainer?.classList.add('show');
    }
    if (supportChatBtn) {
      supportChatBtn.forEach(item => {
        item.addEventListener('click', () => {
          supportChat.classList.toggle('show-chat');

          supportChatBtn[supportChatBtn.length - 1].classList.toggle(
            'btn-chat-close'
          );

          supportChatcontainer.classList.add('show');
        });
      });
    }
  };

  /* eslint-disable no-new */
  /*-----------------------------------------------
  |                    Swiper
  -----------------------------------------------*/

  const swiperInit = () => {
    const { getData } = window.phoenix.utils;
    const swiperContainers = document.querySelectorAll('.swiper-theme-container');
    if (swiperContainers) {
      swiperContainers.forEach(swiperContainer => {
        const swiper = swiperContainer.querySelector('[data-swiper]');
        const options = getData(swiper, 'swiper');
        const thumbsOptions = options.thumb;
        let thumbsInit;
        if (thumbsOptions) {
          const thumbImages = swiper.querySelectorAll('img');
          let slides = '';
          thumbImages.forEach(img => {
            slides += `
          <div class='swiper-slide'>
            <img class='img-fluid rounded mt-2' src=${img.src} alt=''/>
          </div>
        `;
          });

          const thumbs = document.createElement('div');
          thumbs.setAttribute('class', 'swiper thumb');
          thumbs.innerHTML = `<div class='swiper-wrapper'>${slides}</div>`;

          if (thumbsOptions.parent) {
            const parent = document.querySelector(thumbsOptions.parent);
            parent.parentNode.appendChild(thumbs);
          } else {
            swiper.parentNode.appendChild(thumbs);
          }

          thumbsInit = new window.Swiper(thumbs, thumbsOptions);
        }
        const swiperNav = swiperContainer.querySelector('.swiper-nav');
        new window.Swiper(swiper, {
          ...options,
          navigation: {
            nextEl: swiperNav?.querySelector('.swiper-button-next'),
            prevEl: swiperNav?.querySelector('.swiper-button-prev')
          },
          thumbs: {
            swiper: thumbsInit
          }
        });
        const gallerySlider = document.querySelector('.swiper-slider-gallery');
        if (gallerySlider) {
          window.addEventListener('resize', () => {
            thumbsInit.update();
          });
        }
      });
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                                Theme Control                               */
  /* -------------------------------------------------------------------------- */
  /* eslint-disable no-param-reassign */
  /* eslint-disable */
  const { config } = window.config;

  const initialDomSetup = element => {
    const { getData, getItemFromStore, getSystemTheme } = window.phoenix.utils;
    if (!element) return;

    element.querySelectorAll('[data-theme-control]').forEach(el => {
      const inputDataAttributeValue = getData(el, 'theme-control');
      const localStorageValue = getItemFromStore(inputDataAttributeValue);

      // diable horizontal navbar shape for dual nav
      if (
        inputDataAttributeValue === 'phoenixNavbarTopShape' &&
        getItemFromStore('phoenixNavbarPosition') === 'dual-nav'
      ) {
        el.setAttribute('disabled', true);
      }

      // diable navbar vertical style for horizontal & dual navbar
      const currentNavbarPosition = getItemFromStore('phoenixNavbarPosition');
      const isHorizontalOrDualNav =
        currentNavbarPosition === 'horizontal' ||
        currentNavbarPosition === 'dual-nav';
      if (
        inputDataAttributeValue === 'phoenixNavbarVerticalStyle' &&
        isHorizontalOrDualNav
      ) {
        el.setAttribute('disabled', true);
      }

      if (el.type === 'checkbox') {
        if (inputDataAttributeValue === 'phoenixTheme') {
          if (
            localStorageValue === 'auto'
              ? getSystemTheme() === 'dark'
              : localStorageValue === 'dark'
          ) {
            el.setAttribute('checked', true);
          }
        } else {
          localStorageValue && el.setAttribute('checked', true);
        }
      } else if (
        el.type === 'radio' &&
        inputDataAttributeValue === 'phoenixNavbarVerticalStyle'
      ) {
        localStorageValue === 'darker' &&
          el.value === 'darker' &&
          el.setAttribute('checked', true);
        localStorageValue === 'default' &&
          el.value === 'default' &&
          el.setAttribute('checked', true);
      } else if (
        el.type === 'radio' &&
        inputDataAttributeValue === 'phoenixNavbarTopShape'
      ) {
        localStorageValue === 'slim' &&
          el.value === 'slim' &&
          el.setAttribute('checked', true);
        localStorageValue === 'default' &&
          el.value === 'default' &&
          el.setAttribute('checked', true);
      } else if (
        el.type === 'radio' &&
        inputDataAttributeValue === 'phoenixNavbarTopStyle'
      ) {
        localStorageValue === 'darker' &&
          el.value === 'darker' &&
          el.setAttribute('checked', true);
        localStorageValue === 'default' &&
          el.value === 'default' &&
          el.setAttribute('checked', true);
      } else if (
        el.type === 'radio' &&
        inputDataAttributeValue === 'phoenixTheme'
      ) {
        const isChecked = localStorageValue === el.value;
        isChecked && el.setAttribute('checked', true);
      } else if (
        el.type === 'radio' &&
        inputDataAttributeValue === 'phoenixNavbarPosition'
      ) {
        const isChecked = localStorageValue === el.value;
        isChecked && el.setAttribute('checked', true);
      } else {
        const isActive = localStorageValue === el.value;
        isActive && el.classList.add('active');
      }
    });
  };

  const changeTheme = element => {
    const { getData, getItemFromStore, getSystemTheme } = window.phoenix.utils;

    element
      .querySelectorAll('[data-theme-control = "phoenixTheme"]')
      .forEach(el => {
        const inputDataAttributeValue = getData(el, 'theme-control');
        const localStorageValue = getItemFromStore(inputDataAttributeValue);

        if (el.type === 'checkbox') {
          if (localStorageValue === 'auto') {
            getSystemTheme() === 'dark'
              ? (el.checked = true)
              : (el.checked = false);
          } else {
            localStorageValue === 'dark'
              ? (el.checked = true)
              : (el.checked = false);
          }
        } else if (el.type === 'radio') {
          localStorageValue === el.value
            ? (el.checked = true)
            : (el.checked = false);
        } else {
          localStorageValue === el.value
            ? el.classList.add('active')
            : el.classList.remove('active');
        }
      });
  };

  const handleThemeDropdownIcon = value => {
    document.querySelectorAll('[data-theme-dropdown-toggle-icon]').forEach(el => {
      el.classList.toggle(
        'd-none',
        value !== el.getAttribute('data-theme-dropdown-toggle-icon')
        // value !== getData(el, 'theme-dropdown-toggle-icon')
      );
    });
  };

  handleThemeDropdownIcon(localStorage.getItem('phoenixTheme'));

  const themeControl = () => {
    const { getData, getItemFromStore, getSystemTheme } = window.phoenix.utils;
    // handleThemeDropdownIcon(
    //   window.phoenix.utils.getItemFromStore('phoenixTheme'),
    //   getData
    // );

    const handlePageUrl = el => {
      const pageUrl = getData(el, 'page-url');
      if (pageUrl) {
        window.location.replace(pageUrl);
      } else {
        window.location.reload();
      }
    };

    const themeController = new DomNode(document.body);

    const navbarVertical = document.querySelector('.navbar-vertical');
    const navbarTop = document.querySelector('.navbar-top');
    const supportChat = document.querySelector('.support-chat-container');
    initialDomSetup(themeController.node);

    themeController.on('click', e => {
      const target = new DomNode(e.target);

      if (target.data('theme-control')) {
        const control = target.data('theme-control');

        let value = e.target[e.target.type === 'checkbox' ? 'checked' : 'value'];

        if (control === 'phoenixTheme') {
          typeof value === 'boolean' && (value = value ? 'dark' : 'light');
        }

        // config.hasOwnProperty(control) && setItemToStore(control, value);
        config.hasOwnProperty(control) &&
          window.config.set({
            [control]: value
          });

        switch (control) {
          case 'phoenixTheme': {
            document.documentElement.setAttribute(
              'data-bs-theme',
              value === 'auto' ? getSystemTheme() : value
            );
            // document.documentElement.classList[
            //   value === 'dark' ? 'add' : 'remove'
            // ]('dark');
            const clickControl = new CustomEvent('clickControl', {
              detail: { control, value }
            });
            e.currentTarget.dispatchEvent(clickControl);
            changeTheme(themeController.node);
            break;
          }
          case 'phoenixNavbarVerticalStyle': {
            navbarVertical.setAttribute('data-navbar-appearance', 'default');
            if (value !== 'default') {
              navbarVertical.setAttribute('data-navbar-appearance', 'darker');
            }
            break;
          }
          case 'phoenixNavbarTopStyle': {
            navbarTop.setAttribute('data-navbar-appearance', 'default');
            if (value !== 'default') {
              navbarTop.setAttribute('data-navbar-appearance', 'darker');
            }
            break;
          }
          case 'phoenixNavbarTopShape':
            {
              if (getItemFromStore('phoenixNavbarPosition') === 'dual-nav') {
                el.setAttribute('disabled', true);
                // document.documentElement.setAttribute("data-bs-theme", value);
              } else handlePageUrl(target.node);
            }
            break;
          case 'phoenixNavbarPosition':
            {
              handlePageUrl(target.node);
            }

            break;
          case 'phoenixIsRTL':
            {
              // localStorage.setItem('phoenixIsRTL', target.node.checked);
              window.config.set({
                phoenixIsRTL: target.node.checked
              });
              window.location.reload();
            }
            break;

          case 'phoenixSupportChat': {
            supportChat?.classList.remove('show');
            if (value) {
              supportChat?.classList.add('show');
            }
            break;
          }

          case 'reset': {
            window.config.reset();
            window.location.reload();
            break;
          }

          default: {
            window.location.reload();
          }
        }
      }
    });

    themeController.on('clickControl', ({ detail: { control, value } }) => {
      if (control === 'phoenixTheme') {
        handleThemeDropdownIcon(value);
      }
    });
  };

  const { merge } = window._;

  /* -------------------------------------------------------------------------- */
  /*                                   Tinymce                                  */
  /* -------------------------------------------------------------------------- */

  const tinymceInit = () => {
    const { getColor, getData, getItemFromStore } = window.phoenix.utils;

    const tinymces = document.querySelectorAll('[data-tinymce]');

    if (window.tinymce) {
      // const wrapper = document.querySelector('.tox-sidebar-wrap');
      tinymces.forEach(tinymceEl => {
        const userOptions = getData(tinymceEl, 'tinymce');
        const options = merge(
          {
            selector: '.tinymce',
            height: '50vh',
            skin: 'oxide',
            menubar: false,
            content_style: `
        .mce-content-body { 
          color: ${getColor('emphasis-color')};
          background-color: ${getColor('tinymce-bg')};
        }
        .mce-content-body[data-mce-placeholder]:not(.mce-visualblocks)::before {
          color: ${getColor('quaternary-color')};
          font-weight: 400;
          font-size: 12.8px;
        }
        `,
            // mobile: {
            //   theme: 'mobile',
            //   toolbar: ['undo', 'bold']
            // },
            statusbar: false,
            plugins: 'link,image,lists,table,media',
            theme_advanced_toolbar_align: 'center',
            directionality: getItemFromStore('phoenixIsRTL') ? 'rtl' : 'ltr',
            toolbar: [
              { name: 'history', items: ['undo', 'redo'] },
              {
                name: 'formatting',
                items: ['bold', 'italic', 'underline', 'strikethrough']
              },
              {
                name: 'alignment',
                items: ['alignleft', 'aligncenter', 'alignright', 'alignjustify']
              },
              { name: 'list', items: ['numlist', 'bullist'] },
              { name: 'link', items: ['link'] }
            ],
            setup: editor => {
              editor.on('focus', () => {
                const wraper = document.querySelector('.tox-sidebar-wrap');
                wraper.classList.add('editor-focused');
              });
              editor.on('blur', () => {
                const wraper = document.querySelector('.tox-sidebar-wrap');
                wraper.classList.remove('editor-focused');
              });
            }
          },
          userOptions
        );
        window.tinymce.init(options);
      });

      const themeController = document.body;
      if (themeController) {
        themeController.addEventListener(
          'clickControl',
          ({ detail: { control } }) => {
            if (control === 'phoenixTheme') {
              tinymces.forEach(tinymceEl => {
                const instance = window.tinymce.get(tinymceEl.id);
                instance.dom.addStyle(
                  `.mce-content-body{
                  color: ${getColor('emphasis-color')} !important;
                  background-color: ${getColor('tinymce-bg')} !important;
                }`
                );
              });
            }
          }
        );
      }
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                                    Toast                                   */
  /* -------------------------------------------------------------------------- */

  const toastInit = () => {
    const toastElList = [].slice.call(document.querySelectorAll('.toast'));
    toastElList.map(toastEl => new bootstrap.Toast(toastEl));

    const liveToastBtn = document.getElementById('liveToastBtn');

    if (liveToastBtn) {
      const liveToast = new bootstrap.Toast(document.getElementById('liveToast'));

      liveToastBtn.addEventListener('click', () => {
        liveToast && liveToast.show();
      });
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                                    TODO Offacanvas                                   */
  /* -------------------------------------------------------------------------- */

  const todoOffcanvasInit = () => {
    const { getData } = window.phoenix.utils;

    const stopPropagationElements = document.querySelectorAll(
      '[data-event-propagation-prevent]'
    );

    if (stopPropagationElements) {
      stopPropagationElements.forEach(el => {
        el.addEventListener('click', e => {
          e.stopPropagation();
        });
      });
    }

    const todoList = document.querySelector('.todo-list');

    if (todoList) {
      const offcanvasToggles = todoList.querySelectorAll(
        '[data-todo-offcanvas-toogle]'
      );

      offcanvasToggles.forEach(toggle => {
        const target = getData(toggle, 'todo-offcanvas-target');
        const offcanvasEl = todoList.querySelector(`#${target}`);
        const todoOffcanvas = new window.bootstrap.Offcanvas(offcanvasEl, {
          backdrop: true
        });
        toggle.addEventListener('click', () => {
          todoOffcanvas.show();
        });
      });
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                                   Tooltip                                  */
  /* -------------------------------------------------------------------------- */
  const tooltipInit = () => {
    const tooltipTriggerList = [].slice.call(
      document.querySelectorAll('[data-bs-toggle="tooltip"]')
    );

    tooltipTriggerList.map(
      tooltipTriggerEl =>
        new bootstrap.Tooltip(tooltipTriggerEl, {
          trigger: 'hover'
        })
    );
  };

  /* eslint-disable no-restricted-syntax */
  /* -------------------------------------------------------------------------- */
  /*                                 step wizard                                */
  /* -------------------------------------------------------------------------- */
  const wizardInit = () => {
    const { getData } = window.phoenix.utils;

    const selectors = {
      WIZARDS: '[data-theme-wizard]',
      TOGGLE_BUTTON_EL: '[data-wizard-step]',
      FORMS: '[data-wizard-form]',
      PASSWORD_INPUT: '[data-wizard-password]',
      CONFIRM_PASSWORD_INPUT: '[data-wizard-confirm-password]',
      NEXT_BTN: '[data-wizard-next-btn]',
      PREV_BTN: '[data-wizard-prev-btn]',
      FOOTER: '[data-wizard-footer]'
    };

    const events = {
      SUBMIT: 'submit',
      SHOW: 'show.bs.tab',
      SHOWN: 'shown.bs.tab',
      CLICK: 'click'
    };

    const wizards = document.querySelectorAll(selectors.WIZARDS);

    wizards.forEach(wizard => {
      const tabToggleButtonEl = wizard.querySelectorAll(
        selectors.TOGGLE_BUTTON_EL
      );
      const forms = wizard.querySelectorAll(selectors.FORMS);
      const passwordInput = wizard.querySelector(selectors.PASSWORD_INPUT);
      const confirmPasswordInput = wizard.querySelector(
        selectors.CONFIRM_PASSWORD_INPUT
      );
      const nextButton = wizard.querySelector(selectors.NEXT_BTN);
      const prevButton = wizard.querySelector(selectors.PREV_BTN);
      const wizardFooter = wizard.querySelector(selectors.FOOTER);
      const submitEvent = new Event(events.SUBMIT, {
        bubbles: true,
        cancelable: true
      });
      const hasWizardModal = wizard.hasAttribute('data-wizard-modal-disabled');

      const tabs = Array.from(tabToggleButtonEl).map(item => {
        return window.bootstrap.Tab.getOrCreateInstance(item);
      });
      // console.log({ tabs });

      let count = 0;
      let showEvent = null;

      forms.forEach(form => {
        form.addEventListener(events.SUBMIT, e => {
          e.preventDefault();
          if (form.classList.contains('needs-validation')) {
            if (passwordInput && confirmPasswordInput) {
              if (passwordInput.value !== confirmPasswordInput.value) {
                confirmPasswordInput.setCustomValidity('Invalid field.');
              } else {
                confirmPasswordInput.setCustomValidity('');
              }
            }
            if (!form.checkValidity()) {
              showEvent.preventDefault();
              return false;
            }
          }
          count += 1;
          return null;
        });
      });

      nextButton.addEventListener(events.CLICK, () => {
        if (count + 1 < tabs.length) {
          tabs[count + 1].show();
        }
      });

      if (prevButton) {
        prevButton.addEventListener(events.CLICK, () => {
          count -= 1;
          tabs[count].show();
        });
      }

      if (tabToggleButtonEl.length) {
        tabToggleButtonEl.forEach((item, index) => {
          item.addEventListener(events.SHOW, e => {
            const step = getData(item, 'wizard-step');
            showEvent = e;
            if (step > count) {
              forms[count].dispatchEvent(submitEvent);
            }
          });
          item.addEventListener(events.SHOWN, () => {
            count = index;
            // can't go back tab
            if (count === tabToggleButtonEl.length - 1 && !hasWizardModal) {
              tabToggleButtonEl.forEach(tab => {
                tab.setAttribute('data-bs-toggle', 'modal');
                tab.setAttribute('data-bs-target', '#error-modal');
              });
            }
            // add done class
            for (let i = 0; i < count; i += 1) {
              tabToggleButtonEl[i].classList.add('done');
              if (i > 0) {
                tabToggleButtonEl[i - 1].classList.add('complete');
              }
            }
            // remove done class
            for (let j = count; j < tabToggleButtonEl.length; j += 1) {
              tabToggleButtonEl[j].classList.remove('done');
              if (j > 0) {
                tabToggleButtonEl[j - 1].classList.remove('complete');
              }
            }

            // card footer remove at last step
            if (count > tabToggleButtonEl.length - 2) {
              wizardFooter.classList.add('d-none');
            } else {
              wizardFooter.classList.remove('d-none');
            }
            // prev-button removing
            if (prevButton) {
              if (count > 0 && count !== tabToggleButtonEl.length - 1) {
                prevButton.classList.remove('d-none');
              } else {
                prevButton.classList.add('d-none');
              }
            }
          });
        });
      }
    });
  };

  const faqTabInit = () => {
    const triggerEls = document.querySelectorAll('[data-vertical-category-tab]');
    const offcanvasEle = document.querySelector(
      '[data-vertical-category-offcanvas]'
    );
    const filterEles = document.querySelectorAll('[data-category-filter]');
    const faqSubcategoryTabs = document.querySelectorAll(
      '.faq-subcategory-tab .nav-item'
    );

    if (offcanvasEle) {
      const offcanvas =
        window.bootstrap.Offcanvas?.getOrCreateInstance(offcanvasEle);

      triggerEls.forEach(el => {
        el.addEventListener('click', () => {
          offcanvas.hide();
        });
      });
    }

    if (filterEles) {
      filterEles.forEach(el => {
        if (el.classList.contains('active')) {
          faqSubcategoryTabs.forEach(item => {
            if (
              !item.classList.contains(el.getAttribute('data-category-filter')) &&
              el.getAttribute('data-category-filter') !== 'all'
            ) {
              item.classList.add('d-none');
            }
          });
        }
        el.addEventListener('click', () => {
          faqSubcategoryTabs.forEach(item => {
            if (el.getAttribute('data-category-filter') === 'all') {
              item.classList.remove('d-none');
            } else if (
              !item.classList.contains(el.getAttribute('data-category-filter'))
            ) {
              item.classList.add('d-none');
            }
          });
        });
      });
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                                    Kanban                                  */
  /* -------------------------------------------------------------------------- */

  const kanbanInit = () => {
    // kanbanContainer to controll collapse behavior in kanban board
    const kanbanContainer = document.querySelector('[data-kanban-container]');
    if (kanbanContainer) {
      kanbanContainer.addEventListener('click', e => {
        if (e.target.hasAttribute('data-kanban-collapse')) {
          e.target.closest('.kanban-column').classList.toggle('collapsed');
        }
      });

      const kanbanGroups = kanbanContainer.querySelectorAll('[data-sortable]');
      kanbanGroups.forEach(item => {
        const itemInstance = window.Sortable.get(item);
        itemInstance.option('onStart', e => {
          document.body.classList.add('sortable-dragging');
          window.Sortable.ghost
            .querySelector('.dropdown-menu')
            .classList.remove('show');
          const dropdownElement = e.item.querySelector(
            `[data-bs-toggle='dropdown']`
          );
          window.bootstrap.Dropdown.getInstance(dropdownElement)?.hide();
        });

        // return itemInstance;
      });
    }
  };

  const towFAVerificarionInit = () => {
    const verificationForm = document.querySelector('[data-2fa-form]');
    const inputFields = verificationForm?.querySelectorAll('input[type=number]');
    const varificationBtn = verificationForm?.querySelector(
      'button[type=submit]'
    );

    if (verificationForm) {
      window.addEventListener('load', () => inputFields[0].focus());
      const totalInputLength = 6;
      inputFields.forEach((input, index) => {
        input.addEventListener('keyup', e => {
          const { value } = e.target;
          if (value) {
            [...value].slice(0, totalInputLength).forEach((char, charIndex) => {
              if (inputFields && inputFields[index + charIndex]) {
                inputFields[index + charIndex].value = char;
                inputFields[index + charIndex + 1]?.focus();
              }
            });
          } else {
            inputFields[index].value = '';
            inputFields[index - 1]?.focus();
          }
          const inputs = [...inputFields];
          const updatedOtp = inputs.reduce(
            (acc, inputData) => acc + (inputData?.value || ''),
            ''
          );
          if (totalInputLength === updatedOtp.length) {
            varificationBtn.removeAttribute('disabled');
          } else {
            varificationBtn.setAttribute('disabled', true);
          }
        });
      });
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                               mapbox                                   */
  /* -------------------------------------------------------------------------- */

  const mapboxInit = () => {
    const { getData } = window.phoenix.utils;
    const mapboxContainers = document.querySelectorAll('.mapbox-container');
    const mapContainerTab = document.querySelectorAll('[data-tab-map-container]');
    if (mapboxContainers) {
      mapboxContainers.forEach(mapboxContainer => {
        window.mapboxgl.accessToken =
          'pk.eyJ1IjoidGhlbWV3YWdvbiIsImEiOiJjbGhmNW5ybzkxcmoxM2RvN2RmbW1nZW90In0.hGIvQ890TYkZ948MVrsMIQ';

        const mapbox = mapboxContainer.querySelector('[data-mapbox]');
        if (mapbox) {
          const options = getData(mapbox, 'mapbox');

          const zoomIn = document.querySelector('.zoomIn');
          const zoomOut = document.querySelector('.zoomOut');
          const fullScreen = document.querySelector('.fullScreen');

          const styles = {
            default: 'mapbox://styles/mapbox/light-v11',
            light: 'mapbox://styles/themewagon/clj57pads001701qo25756jtw',
            dark: 'mapbox://styles/themewagon/cljzg9juf007x01pk1bepfgew'
          };

          const map = new window.mapboxgl.Map({
            ...options,
            container: 'mapbox',
            style: styles[window.config.config.phoenixTheme]
          });

          if (options.center) {
            new window.mapboxgl.Marker({
              color: getColor('danger')
            })
              .setLngLat(options.center)
              .addTo(map);
          }

          if (zoomIn && zoomOut) {
            zoomIn.addEventListener('click', () => map.zoomIn());
            zoomOut.addEventListener('click', () => map.zoomOut());
          }
          if (fullScreen) {
            fullScreen.addEventListener('click', () =>
              map.getContainer().requestFullscreen()
            );
          }

          mapContainerTab.forEach(ele => {
            ele.addEventListener('shown.bs.tab', () => {
              map.resize();
            });
          });
        }
      });
    }
  };

  const themeController$2 = document.body;
  if (themeController$2) {
    themeController$2.addEventListener('clickControl', () => {
      mapboxInit();
    });
  }

  const flightMapInit = () => {
    const flightMap = document.querySelector('#flightMap');
    if (flightMap) {
      window.mapboxgl.accessToken =
        'pk.eyJ1IjoidGhlbWV3YWdvbiIsImEiOiJjbGhmNW5ybzkxcmoxM2RvN2RmbW1nZW90In0.hGIvQ890TYkZ948MVrsMIQ';

      const zoomIn = document.querySelector('.zoomIn');
      const zoomOut = document.querySelector('.zoomOut');
      const fullScreen = document.querySelector('.fullScreen');

      const styles = {
        default: 'mapbox://styles/mapbox/light-v11',
        light: 'mapbox://styles/themewagon/clj57pads001701qo25756jtw',
        dark: 'mapbox://styles/themewagon/cljzg9juf007x01pk1bepfgew'
      };

      const map = new window.mapboxgl.Map({
        container: 'flightMap',
        style: styles[window.config.config.phoenixTheme],
        center: [-73.102712, 7.102257],
        zoom: 5,
        pitch: 40,
        attributionControl: false
      });

      zoomIn.addEventListener('click', () => map.zoomIn());
      zoomOut.addEventListener('click', () => map.zoomOut());
      fullScreen.addEventListener('click', () =>
        map.getContainer().requestFullscreen()
      );

      const origin = [-61.100583, 5.044713];
      const currentPosition = [-74.2139449434892, 8.136553550752552];
      const destination = [-84.913785, 10.325774];

      const originToCurrentRoute = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: {
              type: 'LineString',
              coordinates: [origin, currentPosition]
            }
          }
        ]
      };
      const currentToDestinationRoute = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: {
              type: 'LineString',
              coordinates: [currentPosition, destination]
            }
          }
        ]
      };

      const points = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            properties: {},
            geometry: {
              type: 'Point',
              coordinates: origin
            }
          },
          {
            type: 'Feature',
            properties: {},
            geometry: {
              type: 'Point',
              coordinates: currentPosition
            }
          },
          {
            type: 'Feature',
            properties: {},
            geometry: {
              type: 'Point',
              coordinates: destination
            }
          }
        ]
      };

      let count = 1;
      points.features.forEach(feature => {
        const el = document.createElement('div');
        el.className = `marker-${count}`;
        new window.mapboxgl.Marker(el)
          .setLngLat(feature.geometry.coordinates)
          .addTo(map);
        count += 1;
      });

      const lineDistance = window.turf.length(originToCurrentRoute.features[0]);
      const lineDistance2 = window.turf.length(originToCurrentRoute.features[0]);

      const arc = [];
      const arc2 = [];

      const steps = 500;

      for (let i = 0; i < lineDistance; i += lineDistance / steps) {
        const segment = window.turf.along(originToCurrentRoute.features[0], i);
        arc.push(segment.geometry.coordinates);
      }
      for (let i = 0; i < lineDistance2; i += lineDistance2 / steps) {
        const segment = window.turf.along(
          currentToDestinationRoute.features[0],
          i
        );
        arc2.push(segment.geometry.coordinates);
      }

      originToCurrentRoute.features[0].geometry.coordinates = arc;
      currentToDestinationRoute.features[0].geometry.coordinates = arc2;

      map.on('load', () => {
        map.addSource('route', {
          type: 'geojson',
          data: originToCurrentRoute.features[0]
        });
        map.addSource('route2', {
          type: 'geojson',
          data: currentToDestinationRoute.features[0]
        });

        map.addLayer({
          id: 'route',
          source: 'route',
          type: 'line',
          paint: {
            'line-width': 2,
            'line-color':
              getItemFromStore('phoenixTheme') === 'dark'
                ? getColor('primary')
                : getColor('primary-light')
          }
        });
        map.addLayer({
          id: 'route2',
          source: 'route2',
          type: 'line',
          paint: {
            'line-width': 1,
            'line-color': getColor('warning')
          }
        });
      });
    }
  };

  const themeController$1 = document.body;
  if (themeController$1) {
    themeController$1.addEventListener('clickControl', () => {
      flightMapInit();
    });
  }

  /* -------------------------------------------------------------------------- */
  /*                                 Typed Text                                 */
  /* -------------------------------------------------------------------------- */

  const typedTextInit = () => {
    const typedTexts = document.querySelectorAll('.typed-text');
    if (typedTexts.length && window.Typed) {
      typedTexts.forEach(typedText => {
        return new window.Typed(typedText, {
          strings: getData(typedText, 'typedText'),
          typeSpeed: 70,
          backSpeed: 70,
          loop: true,
          backDelay: 1000
        });
      });
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                               price tier form                                   */
  /* -------------------------------------------------------------------------- */

  const priceTierFormInit = () => {
    const priceTierForms = document.querySelectorAll('[data-form-price-tier]');
    if (priceTierForms) {
      priceTierForms.forEach(priceTierForm => {
        const priceToggler = priceTierForm.querySelector('[data-price-toggle]');
        const pricings = priceTierForm.querySelectorAll('[data-pricing]');
        const bottomOption = priceTierForm.querySelector(
          '[data-pricing-collapse]'
        );

        const pricingCollapse = new window.bootstrap.Collapse(bottomOption, {
          toggle: false
        });

        priceToggler.addEventListener('change', e => {
          pricings[0].checked = true;
          if (e.target.checked) {
            priceTierForm.classList.add('active');
          } else {
            priceTierForm.classList.remove('active');
            pricingCollapse.hide();
          }
        });
        pricings.forEach(pricing => {
          pricing.addEventListener('change', e => {
            if (e.target.value === 'paid') {
              pricingCollapse.show();
            } else {
              pricingCollapse.hide();
            }
          });
        });
      });
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                               noUiSlider                                   */
  /* -------------------------------------------------------------------------- */
  const nouisliderInit = () => {
    const { getData } = window.phoenix.utils;
    if (window.noUiSlider) {
      const elements = document.querySelectorAll('[data-nouislider]');
      elements.forEach(item => {
        const userOptions = getData(item, 'nouislider');
        const sliderValues = getData(item, 'nouislider-values');
        let defaultOptions;
        if (sliderValues && sliderValues.length) {
          defaultOptions = {
            connect: true,
            step: 1,
            range: { min: 0, max: sliderValues.length - 1 },
            tooltips: true,
            format: {
              to(value) {
                return sliderValues[Math.round(value)];
              },
              from(value) {
                return sliderValues.indexOf(value);
              }
            }
          };
        } else {
          defaultOptions = {
            start: [10],
            connect: [true, false],
            step: 1,
            range: { min: [0], max: [100] },
            tooltips: true
          };
        }
        const options = window._.merge(defaultOptions, userOptions);
        window.noUiSlider.create(item, { ...options });
      });
    }
  };

  const collapseAllInit = () => {
    const collapseParent = document.querySelector('[data-collapse-all]');
    const collapseBtn = document.querySelector('[data-btn-collapse-all]');
    if (collapseParent) {
      const collapseElements = collapseParent.querySelectorAll('.collapse');
      collapseElements.forEach(ele => {
        const collapse = window.bootstrap.Collapse.getOrCreateInstance(ele, {
          toggle: false
        });
        collapseBtn.addEventListener('click', () => {
          collapse.hide();
        });
      });
    }
  };

  const leaftletPoints = [
    {
      lat: 53.958332,
      long: -1.080278,
      name: 'Diana Meyer',
      street: 'Slude Strand 27',
      location: '1130 Kobenhavn'
    },
    {
      lat: 52.958332,
      long: -1.080278,
      name: 'Diana Meyer',
      street: 'Slude Strand 27',
      location: '1130 Kobenhavn'
    },
    {
      lat: 51.958332,
      long: -1.080278,
      name: 'Diana Meyer',
      street: 'Slude Strand 27',
      location: '1130 Kobenhavn'
    },
    {
      lat: 53.958332,
      long: -1.080278,
      name: 'Diana Meyer',
      street: 'Slude Strand 27',
      location: '1130 Kobenhavn'
    },
    {
      lat: 54.958332,
      long: -1.080278,
      name: 'Diana Meyer',
      street: 'Slude Strand 27',
      location: '1130 Kobenhavn'
    },
    {
      lat: 55.958332,
      long: -1.080278,
      name: 'Diana Meyer',
      street: 'Slude Strand 27',
      location: '1130 Kobenhavn'
    },
    {
      lat: 53.908332,
      long: -1.080278,
      name: 'Diana Meyer',
      street: 'Slude Strand 27',
      location: '1130 Kobenhavn'
    },
    {
      lat: 53.008332,
      long: -1.080278,
      name: 'Diana Meyer',
      street: 'Slude Strand 27',
      location: '1130 Kobenhavn'
    },
    {
      lat: 53.158332,
      long: -1.080278,
      name: 'Diana Meyer',
      street: 'Slude Strand 27',
      location: '1130 Kobenhavn'
    },
    {
      lat: 53.000032,
      long: -1.080278,
      name: 'Diana Meyer',
      street: 'Slude Strand 27',
      location: '1130 Kobenhavn'
    },
    {
      lat: 52.292001,
      long: -2.22,
      name: 'Anke Schroder',
      street: 'Industrivej 54',
      location: '4140 Borup'
    },
    {
      lat: 52.392001,
      long: -2.22,
      name: 'Anke Schroder',
      street: 'Industrivej 54',
      location: '4140 Borup'
    },
    {
      lat: 51.492001,
      long: -2.22,
      name: 'Anke Schroder',
      street: 'Industrivej 54',
      location: '4140 Borup'
    },
    {
      lat: 51.192001,
      long: -2.22,
      name: 'Anke Schroder',
      street: 'Industrivej 54',
      location: '4140 Borup'
    },
    {
      lat: 52.292001,
      long: -2.22,
      name: 'Anke Schroder',
      street: 'Industrivej 54',
      location: '4140 Borup'
    },
    {
      lat: 54.392001,
      long: -2.22,
      name: 'Anke Schroder',
      street: 'Industrivej 54',
      location: '4140 Borup'
    },
    {
      lat: 51.292001,
      long: -2.22,
      name: 'Anke Schroder',
      street: 'Industrivej 54',
      location: '4140 Borup'
    },
    {
      lat: 52.102001,
      long: -2.22,
      name: 'Anke Schroder',
      street: 'Industrivej 54',
      location: '4140 Borup'
    },
    {
      lat: 52.202001,
      long: -2.22,
      name: 'Anke Schroder',
      street: 'Industrivej 54',
      location: '4140 Borup'
    },
    {
      lat: 51.063202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 51.363202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 51.463202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 51.563202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 51.763202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 51.863202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 51.963202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 51.000202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 51.000202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 51.163202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 52.263202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 53.463202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 55.163202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 56.263202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 56.463202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 56.563202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 56.663202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 56.763202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 56.863202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 56.963202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 57.973202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 57.163202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 51.163202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 51.263202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 51.363202,
      long: -1.308,
      name: 'Tobias Vogel',
      street: 'Mollebakken 33',
      location: '3650 Olstykke'
    },
    {
      lat: 51.409,
      long: -2.647,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.68,
      long: -1.49,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 50.259998,
      long: -5.051,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 54.906101,
      long: -1.38113,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.383331,
      long: -1.466667,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.483002,
      long: -2.2931,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 51.509865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 51.109865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 51.209865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 51.309865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 51.409865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 51.609865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 51.709865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 51.809865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 51.909865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 52.109865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 52.209865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 52.309865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 52.409865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 52.509865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 52.609865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 52.709865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 52.809865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 52.909865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 52.519865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 52.529865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 52.539865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.549865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 52.549865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.109865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.209865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.319865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.329865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.409865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.559865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.619865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.629865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.639865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.649865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.669865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.669865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.719865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.739865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.749865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.759865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.769865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.769865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.819865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.829865,
      long: -0.118092,
      name: 'Richard Hendricks',
      street: '37 Seafield Place',
      location: 'London'
    },
    {
      lat: 53.483959,
      long: -2.244644,
      name: 'Ethel B. Brooks',
      street: '2576 Sun Valley Road'
    },
    {
      lat: 40.737,
      long: -73.923,
      name: 'Marshall D. Lewis',
      street: '1489 Michigan Avenue',
      location: 'Michigan'
    },
    {
      lat: 39.737,
      long: -73.923,
      name: 'Marshall D. Lewis',
      street: '1489 Michigan Avenue',
      location: 'Michigan'
    },
    {
      lat: 38.737,
      long: -73.923,
      name: 'Marshall D. Lewis',
      street: '1489 Michigan Avenue',
      location: 'Michigan'
    },
    {
      lat: 37.737,
      long: -73.923,
      name: 'Marshall D. Lewis',
      street: '1489 Michigan Avenue',
      location: 'Michigan'
    },
    {
      lat: 40.737,
      long: -73.923,
      name: 'Marshall D. Lewis',
      street: '1489 Michigan Avenue',
      location: 'Michigan'
    },
    {
      lat: 41.737,
      long: -73.923,
      name: 'Marshall D. Lewis',
      street: '1489 Michigan Avenue',
      location: 'Michigan'
    },
    {
      lat: 42.737,
      long: -73.923,
      name: 'Marshall D. Lewis',
      street: '1489 Michigan Avenue',
      location: 'Michigan'
    },
    {
      lat: 43.737,
      long: -73.923,
      name: 'Marshall D. Lewis',
      street: '1489 Michigan Avenue',
      location: 'Michigan'
    },
    {
      lat: 44.737,
      long: -73.923,
      name: 'Marshall D. Lewis',
      street: '1489 Michigan Avenue',
      location: 'Michigan'
    },
    {
      lat: 45.737,
      long: -73.923,
      name: 'Marshall D. Lewis',
      street: '1489 Michigan Avenue',
      location: 'Michigan'
    },
    {
      lat: 46.7128,
      long: 74.006,
      name: 'Elizabeth C. Lyons',
      street: '4553 Kenwood Place',
      location: 'Fort Lauderdale'
    },
    {
      lat: 40.7128,
      long: 74.1181,
      name: 'Elizabeth C. Lyons',
      street: '4553 Kenwood Place',
      location: 'Fort Lauderdale'
    },
    {
      lat: 14.235,
      long: 51.9253,
      name: 'Ralph D. Wylie',
      street: '3186 Levy Court',
      location: 'North Reading'
    },
    {
      lat: 15.235,
      long: 51.9253,
      name: 'Ralph D. Wylie',
      street: '3186 Levy Court',
      location: 'North Reading'
    },
    {
      lat: 16.235,
      long: 51.9253,
      name: 'Ralph D. Wylie',
      street: '3186 Levy Court',
      location: 'North Reading'
    },
    {
      lat: 14.235,
      long: 51.9253,
      name: 'Ralph D. Wylie',
      street: '3186 Levy Court',
      location: 'North Reading'
    },
    {
      lat: 15.8267,
      long: 47.9218,
      name: 'Hope A. Atkins',
      street: '3715 Hillcrest Drive',
      location: 'Seattle'
    },
    {
      lat: 15.9267,
      long: 47.9218,
      name: 'Hope A. Atkins',
      street: '3715 Hillcrest Drive',
      location: 'Seattle'
    },
    {
      lat: 23.4425,
      long: 58.4438,
      name: 'Samuel R. Bailey',
      street: '2883 Raoul Wallenberg Place',
      location: 'Cheshire'
    },
    {
      lat: 23.5425,
      long: 58.3438,
      name: 'Samuel R. Bailey',
      street: '2883 Raoul Wallenberg Place',
      location: 'Cheshire'
    },
    {
      lat: -37.8927369333,
      long: 175.4087452333,
      name: 'Samuel R. Bailey',
      street: '3228 Glory Road',
      location: 'Nashville'
    },
    {
      lat: -38.9064188833,
      long: 175.4441556833,
      name: 'Samuel R. Bailey',
      street: '3228 Glory Road',
      location: 'Nashville'
    },
    {
      lat: -12.409874,
      long: -65.596832,
      name: 'Ann J. Perdue',
      street: '921 Ella Street',
      location: 'Dublin'
    },
    {
      lat: -22.090887,
      long: -57.411827,
      name: 'Jorge C. Woods',
      street: '4800 North Bend River Road',
      location: 'Allen'
    },
    {
      lat: -19.019585,
      long: -65.261963,
      name: 'Russ E. Panek',
      street: '4068 Hartland Avenue',
      location: 'Appleton'
    },
    {
      lat: -16.500093,
      long: -68.214684,
      name: 'Russ E. Panek',
      street: '4068 Hartland Avenue',
      location: 'Appleton'
    },
    {
      lat: -17.413977,
      long: -66.165321,
      name: 'Russ E. Panek',
      street: '4068 Hartland Avenue',
      location: 'Appleton'
    },
    {
      lat: -16.489689,
      long: -68.119293,
      name: 'Russ E. Panek',
      street: '4068 Hartland Avenue',
      location: 'Appleton'
    },
    {
      lat: 54.766323,
      long: 3.08603729,
      name: 'Russ E. Panek',
      street: '4068 Hartland Avenue',
      location: 'Appleton'
    },
    {
      lat: 54.866323,
      long: 3.08603729,
      name: 'Russ E. Panek',
      street: '4068 Hartland Avenue',
      location: 'Appleton'
    },
    {
      lat: 49.537685,
      long: 3.08603729,
      name: 'Russ E. Panek',
      street: '4068 Hartland Avenue',
      location: 'Appleton'
    },
    {
      lat: 54.715424,
      long: 0.509207,
      name: 'Russ E. Panek',
      street: '4068 Hartland Avenue',
      location: 'Appleton'
    },
    {
      lat: 44.891666,
      long: 10.136665,
      name: 'Russ E. Panek',
      street: '4068 Hartland Avenue',
      location: 'Appleton'
    },
    {
      lat: 48.078335,
      long: 14.535004,
      name: 'Russ E. Panek',
      street: '4068 Hartland Avenue',
      location: 'Appleton'
    },
    {
      lat: -26.358055,
      long: 27.398056,
      name: 'Russ E. Panek',
      street: '4068 Hartland Avenue',
      location: 'Appleton'
    },
    {
      lat: -29.1,
      long: 26.2167,
      name: 'Wilbur J. Dry',
      street: '2043 Jadewood Drive',
      location: 'Northbrook'
    },
    {
      lat: -29.883333,
      long: 31.049999,
      name: 'Wilbur J. Dry',
      street: '2043 Jadewood Drive',
      location: 'Northbrook'
    },
    {
      lat: -26.266111,
      long: 27.865833,
      name: 'Wilbur J. Dry',
      street: '2043 Jadewood Drive',
      location: 'Northbrook'
    },
    {
      lat: -29.087217,
      long: 26.154898,
      name: 'Wilbur J. Dry',
      street: '2043 Jadewood Drive',
      location: 'Northbrook'
    },
    {
      lat: -33.958252,
      long: 25.619022,
      name: 'Wilbur J. Dry',
      street: '2043 Jadewood Drive',
      location: 'Northbrook'
    },
    {
      lat: -33.977074,
      long: 22.457581,
      name: 'Wilbur J. Dry',
      street: '2043 Jadewood Drive',
      location: 'Northbrook'
    },
    {
      lat: -26.563404,
      long: 27.844164,
      name: 'Wilbur J. Dry',
      street: '2043 Jadewood Drive',
      location: 'Northbrook'
    },
    {
      lat: 51.21389,
      long: -102.462776,
      name: 'Joseph B. Poole',
      street: '3364 Lunetta Street',
      location: 'Wichita Falls'
    },
    {
      lat: 52.321945,
      long: -106.584167,
      name: 'Joseph B. Poole',
      street: '3364 Lunetta Street',
      location: 'Wichita Falls'
    },
    {
      lat: 50.288055,
      long: -107.793892,
      name: 'Joseph B. Poole',
      street: '3364 Lunetta Street',
      location: 'Wichita Falls'
    },
    {
      lat: 52.7575,
      long: -108.28611,
      name: 'Joseph B. Poole',
      street: '3364 Lunetta Street',
      location: 'Wichita Falls'
    },
    {
      lat: 50.393333,
      long: -105.551941,
      name: 'Joseph B. Poole',
      street: '3364 Lunetta Street',
      location: 'Wichita Falls'
    },
    {
      lat: 50.930557,
      long: -102.807777,
      name: 'Joseph B. Poole',
      street: '3364 Lunetta Street',
      location: 'Wichita Falls'
    },
    {
      lat: 52.856388,
      long: -104.610001,
      name: 'Joseph B. Poole',
      street: '3364 Lunetta Street',
      location: 'Wichita Falls'
    },
    {
      lat: 52.289722,
      long: -106.666664,
      name: 'Joseph B. Poole',
      street: '3364 Lunetta Street',
      location: 'Wichita Falls'
    },
    {
      lat: 52.201942,
      long: -105.123055,
      name: 'Joseph B. Poole',
      street: '3364 Lunetta Street',
      location: 'Wichita Falls'
    },
    {
      lat: 53.278046,
      long: -110.00547,
      name: 'Joseph B. Poole',
      street: '3364 Lunetta Street',
      location: 'Wichita Falls'
    },
    {
      lat: 49.13673,
      long: -102.990959,
      name: 'Joseph B. Poole',
      street: '3364 Lunetta Street',
      location: 'Wichita Falls'
    },
    {
      lat: 45.484531,
      long: -73.597023,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 45.266666,
      long: -71.900002,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 45.349998,
      long: -72.51667,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 47.333332,
      long: -79.433334,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 45.400002,
      long: -74.033333,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 45.683334,
      long: -73.433334,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 48.099998,
      long: -77.783333,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 45.5,
      long: -72.316666,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 46.349998,
      long: -72.550003,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 48.119999,
      long: -69.18,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 45.599998,
      long: -75.25,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 46.099998,
      long: -71.300003,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 45.700001,
      long: -73.633331,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 47.68,
      long: -68.879997,
      name: 'Claudette D. Nowakowski',
      street: '3742 Farland Avenue',
      location: 'San Antonio'
    },
    {
      lat: 46.716667,
      long: -79.099998,
      name: '299'
    },
    {
      lat: 45.016666,
      long: -72.099998,
      name: '299'
    }
  ];

  const { L } = window;

  /* -------------------------------------------------------------------------- */
  /*                                   leaflet                                  */
  /* -------------------------------------------------------------------------- */

  const leafletInit = () => {
    const mapContainer = document.getElementById('map');
    if (L && mapContainer) {
      const getFilterColor = () => {
        return window.config.config.phoenixTheme === 'dark'
          ? [
              'invert:98%',
              'grayscale:69%',
              'bright:89%',
              'contrast:111%',
              'hue:205deg',
              'saturate:1000%'
            ]
          : ['bright:101%', 'contrast:101%', 'hue:23deg', 'saturate:225%'];
      };
      const tileLayerTheme =
        'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';

      const tiles = L.tileLayer.colorFilter(tileLayerTheme, {
        attribution: null,
        transparent: true,
        filter: getFilterColor()
      });

      const map = L.map('map', {
        center: L.latLng(25.659195, 30.182691),
        zoom: 0.6,
        layers: [tiles],
        minZoom: 1.4
      });

      const mcg = L.markerClusterGroup({
        chunkedLoading: false,
        spiderfyOnMaxZoom: false
      });

      leaftletPoints.map(point => {
        const { name, location, street } = point;
        const icon = L.icon({
          iconUrl: `data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABkAAAApCAYAAADAk4LOAAAACXBIWXMAAAFgAAABYAEg2RPaAAADpElEQVRYCZ1XS1LbQBBtybIdiMEJKSpUqihgEW/xDdARyAnirOIl3MBH8NK7mBvkBpFv4Gy9IRSpFIQiRPyNfqkeZkY9HwmFt7Lm06+7p/vN2MmyDIrQ6QebALAHAD4AbFuWfQeAAACGs5H/w5jlsJJw4wMA+GhMFuMA99jIDJJOP+ihZwDQFmNuowWO1wS3viDXpdEdZPEc0odruj0EgN5s5H8tJOEEX8R3rbkMtcU34NTqhe5nSQTJ7Tkk80s6/Gk28scGiULguFBffgdufdEwWoQ0uoXo8hdAlooVH0REjISfwZSlyHGh0V5n6aHAtKTxXI5g6nQnMH0P4bEgwtR18Yw8Pj8QZ4ARUAI0Hl+fQZZGisGEBVwHr7XKzox57DXZ/ij8Cdwe2u057z9/wygOxRl4S2vSUHx1oucaMQGAHTrgtdag9mK5aN+Wx/uAAQ9Zenp/SRce4TpaNbQK4+sTcGqeTB/aIXv3XN5oj2VKqii++U0JunpZ8urxee4hvjqVc2hHpBDXuKKT9XMgVYJ1/1fPGSeaikzgmWWkMIi9bVf8UhotXxzORn5gWFchI8QyttlzjS0qpsaIGY2MMsujV/AUSdcY0dDpB6/EiOPYzclR1CI5mOez3ekHvrFLxa7cR5pTscfrXjk0Vhm5V2PqLUWnH3R5GbPGpMVD7E1ckXesKBQ7AS/vmQ1c0+kHuxpBj98lTCm8pbc5QRJRdZ6qHb/wGryXq3Lxszv+5gySuwvxueXySwYvHEjuQ9ofTGKYlrmK1EsCHMd5SoD7mZ1HHFCBHLNbMEshvrugqWLn01hpVVJhFgVGkDvK7hR6n2B+d9C7xsqWsbkqHv4cCsWezEb+o2SR+SFweUBxfA5wH7kShjKt2vWL57Px3GhIFEezkb8pxvUWHYhotAfCk2AtkEcxoOttrxUWDR5svb1emSQKj0WXK1HYIgFREbiBqmoZcB2RkbE+byMZiosorVgAZF1ID7yQhEs38wa7nUqNDezdlavC2HbBGSQkGgZ8uJVBmzeiKCRRpEa9ilWghORVeGB7BxeSKF5xqbFBkxBrFKUk/JHA7ppENQaCnCjthK+3opCEYyANztXmZN858cDYWSUSHk3A311GAZDvo6deNKUk1EsqnJoQlkYBNlmxQZeaMgmxoUokICoHDce351RCCiuKoirJWEgNOYvQplM2VCLhUqF7jf94rW9kHVUjQeheV4riv0i4ZOzzz/2y/+0KAOAfr4EE4HpCFhwAAAAASUVORK5CYII=`
        });
        const marker = L.marker([point.lat, point.long], {
          icon
        });
        const popupContent = `
        <h6 class="mb-1">${name}</h6>
        <p class="m-0 text-body-quaternary">${street}, ${location}</p>
      `;
        const popup = L.popup({ minWidth: 180 }).setContent(popupContent);
        marker.bindPopup(popup);
        mcg.addLayer(marker);
        return true;
      });
      map.addLayer(mcg);

      const themeController = document.body;
      themeController.addEventListener(
        'clickControl',
        ({ detail: { control, value } }) => {
          if (control === 'phoenixTheme') {
            tiles.updateFilter(
              value === 'dark'
                ? [
                    'invert:98%',
                    'grayscale:69%',
                    'bright:89%',
                    'contrast:111%',
                    'hue:205deg',
                    'saturate:1000%'
                  ]
                : ['bright:101%', 'contrast:101%', 'hue:23deg', 'saturate:225%']
            );
          }
        }
      );
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                                   mapbox cluster                                  */
  /* -------------------------------------------------------------------------- */

  const mapboxClusterInit = () => {
    const mapboxCluster = document.querySelectorAll('#mapbox-cluster');
    if (mapboxCluster) {
      mapboxCluster.forEach(() => {
        window.mapboxgl.accessToken =
          'pk.eyJ1IjoidGhlbWV3YWdvbiIsImEiOiJjbGhmNW5ybzkxcmoxM2RvN2RmbW1nZW90In0.hGIvQ890TYkZ948MVrsMIQ';

        const styles = {
          default: 'mapbox://styles/mapbox/light-v11',
          light: 'mapbox://styles/themewagon/clj57pads001701qo25756jtw',
          dark: 'mapbox://styles/themewagon/cljzg9juf007x01pk1bepfgew'
        };

        const map = new window.mapboxgl.Map({
          container: 'mapbox-cluster',
          style: styles[window.config.config.phoenixTheme],
          center: [-73.102712, 7.102257],
          zoom: 3.5,
          pitch: 40,
          attributionControl: false
        });

        map.on('load', () => {
          map.addSource('earthquakes', {
            type: 'geojson',
            data: 'https://docs.mapbox.com/mapbox-gl-js/assets/earthquakes.geojson',
            cluster: true,
            clusterMaxZoom: 14,
            clusterRadius: 50
          });

          map.addLayer({
            id: 'clusters',
            type: 'circle',
            source: 'earthquakes',
            filter: ['has', 'point_count'],
            paint: {
              'circle-color': [
                'step',
                ['get', 'point_count'],
                getColor('secondary'),
                100,
                getColor('info'),
                750,
                getColor('warning')
              ],
              'circle-radius': [
                'step',
                ['get', 'point_count'],
                20,
                100,
                30,
                750,
                40
              ]
            }
          });

          map.addLayer({
            id: 'cluster-count',
            type: 'symbol',
            source: 'earthquakes',
            filter: ['has', 'point_count'],
            layout: {
              'text-field': ['get', 'point_count_abbreviated'],
              'text-font': ['DIN Offc Pro Medium', 'Arial Unicode MS Bold'],
              'text-size': 12
            },
            paint: {
              'text-color': getColor('white')
            }
          });

          map.addLayer({
            id: 'unclustered-point',
            type: 'circle',
            source: 'earthquakes',
            filter: ['!', ['has', 'point_count']],
            paint: {
              'circle-color': getColor('primary-light'),
              'circle-radius': 4,
              'circle-stroke-width': 1,
              'circle-stroke-color': getColor('emphasis-bg')
            }
          });

          map.on('click', 'clusters', e => {
            const features = map.queryRenderedFeatures(e.point, {
              layers: ['clusters']
            });
            const clusterId = features[0].properties.cluster_id;
            map
              .getSource('earthquakes')
              .getClusterExpansionZoom(clusterId, (err, zoom) => {
                if (err) return;

                map.easeTo({
                  center: features[0].geometry.coordinates,
                  zoom
                });
              });
          });

          map.on('click', 'unclustered-point', e => {
            const coordinates = e.features[0].geometry.coordinates.slice();
            const { mag } = e.features[0].properties;
            const tsunami = e.features[0].properties.tsunami === 1 ? 'yes' : 'no';

            while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
              coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360;
            }

            new window.mapboxgl.Popup()
              .setLngLat(coordinates)
              .setHTML(`magnitude: ${mag}<br>Was there a tsunami?: ${tsunami}`)
              .addTo(map);
          });

          map.on('mouseenter', 'clusters', () => {
            map.getCanvas().style.cursor = 'pointer';
          });
          map.on('mouseleave', 'clusters', () => {
            map.getCanvas().style.cursor = '';
          });
        });
      });
    }
  };

  const themeController = document.body;
  if (themeController) {
    themeController.addEventListener('clickControl', () => {
      mapboxClusterInit();
    });
  }

  /* -------------------------------------------------------------------------- */
  /*                             Echarts trip review                            */
  /* -------------------------------------------------------------------------- */

  const { echarts } = window;

  const tripReviewChartInit = () => {
    const { getData, getColor } = window.phoenix.utils;
    const $echartTripReviews = document.querySelectorAll('.echart-trip-review');

    if ($echartTripReviews) {
      $echartTripReviews.forEach($echartTripReview => {
        const userOptions = getData($echartTripReview, 'options');
        const chart = echarts.init($echartTripReview);

        const getDefaultOptions = () => ({
          tooltip: {
            trigger: 'item',
            padding: [7, 10],
            backgroundColor: getColor('body-highlight-bg'),
            borderColor: getColor('border-color'),
            textStyle: { color: getColor('light-text-emphasis') },
            borderWidth: 1,
            position: (...params) => handleTooltipPosition(params),
            transitionDuration: 0,
            formatter: params => {
              return `<strong>${params.seriesName}:</strong> ${params.value}%`;
            },
            extraCssText: 'z-index: 1000'
          },
          series: [
            {
              type: 'gauge',
              name: 'Commission',
              startAngle: 90,
              endAngle: -270,
              radius: '90%',
              pointer: {
                show: false
              },
              progress: {
                show: true,
                overlap: false,
                // roundCap: true,
                clip: false,
                itemStyle: {
                  color: getColor('primary')
                }
              },
              axisLine: {
                lineStyle: {
                  width: 4,
                  color: [[1, getColor('secondary-bg')]]
                }
              },
              splitLine: {
                show: false
              },
              axisTick: {
                show: false
              },
              axisLabel: {
                show: false
              },
              detail: {
                fontSize: '20px',
                color: getColor('body-color'),
                offsetCenter: [0, '10%']
              }
            }
          ]
        });

        echartSetOption(chart, userOptions, getDefaultOptions);
      });
    }
  };

  const playOnHoverInit = () => {
    const videos = document.querySelectorAll('[data-play-on-hover]');
    if (videos) {
      videos.forEach(video => {
        video.addEventListener('mouseover', () => {
          video.play();
        });

        video.addEventListener('mouseout', () => {
          video.pause();
        });

        video.addEventListener('touchstart', () => {
          video.play();
        });

        video.addEventListener('touchend', () => {
          video.pause();
        });
      });
    }
  };

  const passwordToggleInit = () => {
    const passwords = document.querySelectorAll('[data-password]');
    if (passwords) {
      passwords.forEach(password => {
        const passwordInput = password.querySelector('[data-password-input]');
        const passwordToggler = password.querySelector('[data-password-toggle]');
        passwordToggler.addEventListener('click', () => {
          if (passwordInput.type === 'password') {
            passwordInput.setAttribute('type', 'text');
            passwordToggler.classList.add('show-password');
          } else {
            passwordInput.setAttribute('type', 'password');
            passwordToggler.classList.remove('show-password');
          }
        });
      });
    }
  };

  /* eslint-disable no-new */

  window.initMap = initMap;
  docReady(detectorInit);
  docReady(simplebarInit);
  docReady(toastInit);
  docReady(tooltipInit);
  docReady(featherIconsInit);
  docReady(basicEchartsInit);
  docReady(bulkSelectInit);
  docReady(listInit);
  docReady(anchorJSInit);
  docReady(popoverInit);
  docReady(formValidationInit);
  docReady(docComponentInit);
  docReady(swiperInit);
  docReady(productDetailsInit);
  docReady(ratingInit);
  docReady(quantityInit);
  docReady(dropzoneInit);
  docReady(choicesInit);
  docReady(tinymceInit);
  docReady(responsiveNavItemsInit);
  docReady(flatpickrInit);
  docReady(iconCopiedInit);
  docReady(isotopeInit);
  docReady(bigPictureInit);
  docReady(countupInit);
  docReady(phoenixOffcanvasInit);
  docReady(todoOffcanvasInit);
  docReady(wizardInit);
  docReady(reportsDetailsChartInit);
  docReady(glightboxInit);
  docReady(themeControl);
  docReady(searchInit);
  docReady(handleNavbarVerticalCollapsed);
  docReady(navbarInit);
  docReady(navbarComboInit);
  docReady(fullCalendarInit);
  docReady(picmoInit);

  docReady(chatInit);
  docReady(modalInit);
  docReady(lottieInit);
  docReady(navbarShadowOnScrollInit);
  docReady(dropdownOnHover);
  docReady(supportChatInit);
  docReady(sortableInit);

  docReady(copyLink);
  docReady(randomColorInit);
  docReady(faqTabInit);
  docReady(createBoardInit);
  docReady(advanceAjaxTableInit);
  docReady(kanbanInit);
  docReady(towFAVerificarionInit);
  docReady(mapboxInit);
  docReady(flightMapInit);
  docReady(typedTextInit);
  docReady(priceTierFormInit);
  docReady(nouisliderInit);
  docReady(collapseAllInit);
  docReady(leafletInit);
  docReady(mapboxClusterInit);
  docReady(tripReviewChartInit);
  docReady(playOnHoverInit);
  docReady(passwordToggleInit);

  docReady(() => {
    const selectedRowsBtn = document.querySelector('[data-selected-rows]');
    const selectedRows = document.getElementById('selectedRows');
    if (selectedRowsBtn) {
      const bulkSelectEl = document.getElementById('bulk-select-example');
      const bulkSelectInstance =
        window.phoenix.BulkSelect.getInstance(bulkSelectEl);
      selectedRowsBtn.addEventListener('click', () => {
        selectedRows.innerHTML = JSON.stringify(
          bulkSelectInstance.getSelectedRows(),
          undefined,
          2
        );
      });
    }
  });

  var phoenix = {
    utils,
    BulkSelect
  };

  return phoenix;

}));
//# sourceMappingURL=phoenix.js.map
