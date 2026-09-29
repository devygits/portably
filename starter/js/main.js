const menuToggle = document.querySelector('[data-js="menu-toggle"]');

if (menuToggle) {
  const navigation = document.getElementById(menuToggle.getAttribute('aria-controls'));

  const setOpen = (open) => {
    menuToggle.setAttribute('aria-expanded', String(open));
    if (navigation) navigation.dataset.open = String(open);
  };

  if (navigation) {
    menuToggle.addEventListener('click', () => {
      setOpen(menuToggle.getAttribute('aria-expanded') !== 'true');
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && menuToggle.getAttribute('aria-expanded') === 'true') {
        setOpen(false);
        menuToggle.focus();
      }
    });
  }
}
