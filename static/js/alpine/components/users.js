document.addEventListener('alpine:init', () => {
    Alpine.data('usersManager', () => ({
        users: [],
        loading: true,

        init() {
            if (window.location.hash === '#users') {
                this.loadUsers();
            }
        },

        modalOpen: false,
        editingUserId: null,

        username: '',
        password: '',
        isAdmin: false,

        get isEditing() {
            return this.editingUserId !== null;
        },

        get modalTitle() {
            return this.isEditing ? 'Edit User' : 'Add User';
        },

        get passwordHint() {
            return this.isEditing
                ? 'Leave empty to keep current password'
                : 'At least 6 characters';
        },

        async loadUsers() {
            this.loading = true;
            try {
                this.users = await Alpine.store('api').get('/users');
            } catch (err) {
                console.error('Failed to load users:', err);
            } finally {
                this.loading = false;
            }
        },

        openAddModal() {
            this.resetForm();
            this.modalOpen = true;
        },

        async openEditModal(userId) {
            try {
                const user = await Alpine.store('api').get(`/users/${userId}`);
                this.editingUserId = userId;
                this.username = user.username;
                this.password = '';
                this.isAdmin = user.is_admin;
                this.modalOpen = true;
            } catch (err) {
                // Error handled by API store
            }
        },

        resetForm() {
            this.editingUserId = null;
            this.username = '';
            this.password = '';
            this.isAdmin = false;
        },

        closeModal() {
            this.modalOpen = false;
            this.resetForm();
        },

        async saveUser() {
            const api = Alpine.store('api');
            const toast = Alpine.store('toast');

            try {
                if (this.isEditing) {
                    await api.put(`/users/${this.editingUserId}`, { is_admin: this.isAdmin });

                    if (this.password) {
                        if (this.password.length < 6) {
                            toast.error('Password must be at least 6 characters');
                            return;
                        }
                        await api.put(`/users/${this.editingUserId}/password`, { password: this.password });
                    }

                    toast.success('User updated');
                } else {
                    if (!this.username || this.username.length < 3) {
                        toast.error('Username must be at least 3 characters');
                        return;
                    }
                    if (!this.password || this.password.length < 6) {
                        toast.error('Password must be at least 6 characters');
                        return;
                    }

                    await api.post('/users', {
                        username: this.username,
                        password: this.password,
                        is_admin: this.isAdmin
                    });

                    toast.success('User created');
                }

                this.closeModal();
                await this.loadUsers();
            } catch (err) {
                // Error handled by API store
            }
        },

        async deleteUser(userId) {
            if (!confirm('Delete this user?')) return;
            try {
                await Alpine.store('api').delete(`/users/${userId}`);
                Alpine.store('toast').success('User deleted');
                await this.loadUsers();
            } catch (err) {
                // Error handled by API store
            }
        }
    }));
});
