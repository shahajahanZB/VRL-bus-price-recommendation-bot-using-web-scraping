# modals.py
from playwright.sync_api import Page

def remove_modals_and_overlays(page: Page):
    """Remove common modal/backdrop elements and unblock page."""
    page.evaluate("""
    () => {
        // Remove known modals/backdrops
        document.querySelectorAll('#largeModal, .banner_modal, .modal.fade.show, .modal-backdrop, .modal, .overlay')
                .forEach(n => n.remove());

        // Hide any extremely high z-index elements
        Array.from(document.querySelectorAll('div')).forEach(d => {
            try {
                const st = window.getComputedStyle(d);
                if ((st.position === 'fixed' || st.position === 'absolute') && parseInt(st.zIndex || 0) > 900) {
                    d.style.pointerEvents = 'none';
                    d.style.display = 'none';
                }
            } catch(e) {}
        });

        document.body.classList.remove('modal-open');
        document.body.style.overflow = 'auto';
    }
    """)
    return True
