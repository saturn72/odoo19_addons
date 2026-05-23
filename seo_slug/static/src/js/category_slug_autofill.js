/** @odoo-module **/
import { CharField } from "@web/views/fields/char/char_field";
import { charField } from "@web/views/fields/char/char_field";
import { registry } from "@web/core/registry";
import { onMounted, onWillUnmount } from "@odoo/owl";

function s72Slugify(text) {
    return (text || '')
        .toLowerCase()
        .replace(/[^\p{L}\d]+/gu, '-')
        .replace(/^-|-$/g, '');
}

class SeoSlugField extends CharField {
    setup() {
        super.setup();
        this._nameInput = null;
        this._nameHandler = null;

        onMounted(() => {
            const scope = this.input.el?.closest('.o_form_renderer') || document;
            const nameInput = scope.querySelector('[name="name"] input');
            if (!nameInput) return;

            this._nameInput = nameInput;
            this._nameHandler = (e) => {
                this.props.record.update({
                    s72_seo_name: s72Slugify(e.target.value),
                });
            };
            nameInput.addEventListener('input', this._nameHandler);
        });

        onWillUnmount(() => {
            this._nameInput?.removeEventListener('input', this._nameHandler);
        });
    }
}

registry.category("fields").add("s72_seo_slug", {
    ...charField,
    component: SeoSlugField,
});
