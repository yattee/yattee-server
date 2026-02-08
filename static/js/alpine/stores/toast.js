document.addEventListener('alpine:init', () => {
    Alpine.store('toast', {
        items: [],
        nextId: 0,

        show(message, type = 'success') {
            const id = this.nextId++;
            this.items.push({ id, message, type });

            setTimeout(() => {
                this.dismiss(id);
            }, 3000);
        },

        dismiss(id) {
            const index = this.items.findIndex(t => t.id === id);
            if (index > -1) {
                this.items.splice(index, 1);
            }
        },

        success(message) { this.show(message, 'success'); },
        error(message) { this.show(message, 'error'); },
        warning(message) { this.show(message, 'warning'); }
    });
});
