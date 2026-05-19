/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, {
    // Intercept when fields are updated in the form UI
    async onRecordChanged(record, changedFields) {
        await super.onRecordChanged(...arguments);

        if (record.resModel === "product.public.category") {

            // Rule: If Name changes, and Slug is blank or hasn't been modified yet, auto-compute it
            if (changedFields.includes("name") && !changedFields.includes("website_slug")) {
                const nameVal = record.data.name || "";
                const autoSlug = this._sanitizeSlugString(nameVal);
                await record.update({ website_slug: autoSlug });
            }

            // Rule: If user manually types/edits the Slug, sanitize their input instantly
            if (changedFields.includes("website_slug")) {
                const currentSlug = record.data.website_slug || "";
                const cleanSlug = this._sanitizeSlugString(currentSlug);

                if (currentSlug !== cleanSlug) {
                    await record.update({ website_slug: cleanSlug });
                }
            }
        }
    },

    /**
     * Your custom parsing rules: lowercase, filter bad characters, compress hyphens
     */
    _sanitizeSlugString(text) {
        return text
            .toLowerCase()
            .replace(/[^a-z0-9_-]/g, "-") // Only allow letters, numbers, hyphens, underscores
            .replace(/-+/g, "-")          // Compress multiple "--" or "---" into a single "-"
            .replace(/-$/, "");           // Strip out any trailing hyphens
    }
});