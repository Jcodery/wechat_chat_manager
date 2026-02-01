document.addEventListener('alpine:init', () => {
    Alpine.data('app', () => ({
        // Auth state
        isLoggedIn: false,
        isFirstTime: true,
        password: '',
        newPassword: '',
        confirmPassword: '',
        
        // Data
        contacts: [],
        chatrooms: [],
        messages: [],
        hiddenContacts: [],
        searchResults: [], // Added for search results
        
        // Selection
        selectedIds: [], 
        currentContact: null,
        
        // Mode
        mode: 'safe', // 'safe' or 'convenient'
        showRiskWarning: false,
        pendingMode: null,
        
        // UI state
        loading: false,
        error: null,
        searchQuery: '',
        showSettings: false,
        showToast: false,
        toastMessage: '',
        toastType: 'info', // 'info', 'success', 'error', 'warning'
        
        // WeChat config
        wechatDir: '',
        hasKey: false,
        accounts: [],
        activeAccount: null,
        manualKey: '',

        // API Configuration
        apiBase: '/api',
        
        // Methods
        async init() {
            console.log('App initialized');
            await this.checkAuthStatus();
            if (this.isLoggedIn) {
                await this.refreshWeChatConfig(true);
                await this.loadContacts();
            }
        },

        // Auth methods
        async checkAuthStatus() {
            try {
                const res = await fetch(`${this.apiBase}/auth/status`);
                if (res.ok) {
                    const data = await res.json();
                    this.isFirstTime = !data.is_set;
                    // If not first time, we might still need to login, so isLoggedIn remains false initially
                    // unless we have a session/token mechanism. Assuming session or re-login required.
                }
            } catch (e) {
                console.error('Auth status check failed', e);
                this.error = '无法连接到服务器';
            }
        },
        
        async login() {
            if (!this.password) {
                this.showNotification('请输入密码', 'error');
                return;
            }
            this.loading = true;
            this.error = null;
            try {
                const res = await fetch(`${this.apiBase}/auth/login`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({password: this.password})
                });
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || '登录失败');
                }
                this.isLoggedIn = true;
                this.showNotification('登录成功', 'success');
                await this.refreshWeChatConfig(true);
                await this.loadContacts();
            } catch (e) {
                this.error = e.message;
                this.showNotification(e.message, 'error');
            } finally {
                this.loading = false;
            }
        },
        
        async setupPassword() {
            if (!this.newPassword || !this.confirmPassword) {
                this.showNotification('请输入密码', 'error');
                return;
            }
            if (this.newPassword !== this.confirmPassword) {
                this.showNotification('两次输入的密码不一致', 'error');
                return;
            }
            this.loading = true;
            try {
                const res = await fetch(`${this.apiBase}/auth/setup`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({password: this.newPassword})
                });
                if (!res.ok) {
                    throw new Error('设置密码失败');
                }
                this.isFirstTime = false;
                this.isLoggedIn = true;
                this.showNotification('密码设置成功', 'success');
                await this.refreshWeChatConfig(true);
                await this.loadContacts();
            } catch (e) {
                this.showNotification(e.message, 'error');
            } finally {
                this.loading = false;
            }
        },

        // WeChat methods
        async refreshWeChatConfig(autoDetectIfMissing = false) {
            // current dir
            try {
                const dirRes = await fetch(`${this.apiBase}/wechat/current-dir`);
                if (dirRes.ok) {
                    const dirData = await dirRes.json();
                    if (dirData && dirData.path) this.wechatDir = dirData.path;
                }
            } catch (e) {
                console.error('Failed to fetch current WeChat dir', e);
            }

            // accounts
            try {
                const accRes = await fetch(`${this.apiBase}/wechat/accounts`);
                if (accRes.ok) {
                    const accData = await accRes.json();
                    this.accounts = accData.accounts || [];
                    this.activeAccount = accData.active_account;
                }
            } catch (e) {
                console.error('Failed to fetch accounts', e);
            }

            // key status
            try {
                const keyRes = await fetch(`${this.apiBase}/wechat/key/status`);
                if (keyRes.ok) {
                    const keyData = await keyRes.json();
                    this.hasKey = !!(keyData && keyData.is_saved);
                }
            } catch (e) {
                console.error('Failed to fetch key status', e);
            }

            if (autoDetectIfMissing && !this.wechatDir) {
                await this.detectWeChatDir(false);
            }
        },

        async setActiveAccount(wxid) {
            try {
                const res = await fetch(`${this.apiBase}/wechat/accounts/active`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ wxid })
                });
                if (!res.ok) {
                    const msg = await this.readApiError(res, '切换账号失败');
                    throw new Error(msg);
                }
                
                await this.refreshWeChatConfig(false);
                await this.loadContacts();
                this.showNotification('已切换账号', 'success');
            } catch (e) {
                this.showNotification(e.message || '切换账号失败', 'error');
            }
        },

        async saveManualKey() {
            if (!this.manualKey || this.manualKey.length !== 64) {
                this.showNotification('请输入有效的64位密钥', 'error');
                return;
            }
            this.loading = true;
            try {
                const res = await fetch(`${this.apiBase}/wechat/key/manual`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: this.manualKey })
                });
                if (!res.ok) {
                    const msg = await this.readApiError(res, '保存密钥失败');
                    throw new Error(msg);
                }
                
                this.manualKey = '';
                await this.refreshWeChatConfig(false);
                this.showNotification('密钥已保存', 'success');
                
                if (this.wechatDir) {
                    await this.loadContacts();
                }
            } catch (e) {
                this.showNotification(e.message || '保存密钥失败', 'error');
            } finally {
                this.loading = false;
            }
        },

        async openSettings() {
            this.showSettings = true;
            await this.refreshWeChatConfig(false);
        },

        async detectWeChatDir(notify = true) {
            try {
                const res = await fetch(`${this.apiBase}/wechat/detect`);
                const data = await res.json().catch(() => ({}));
                if (res.ok && data && data.path) {
                    this.wechatDir = data.path;
                    await this.refreshWeChatConfig(false);
                    if (notify) this.showNotification('已自动检测到微信目录', 'success');
                    if (this.hasKey) await this.loadContacts();
                    return;
                }
                if (notify) {
                    this.showNotification(
                        (data && data.message) || '自动检测失败，请手动填写微信数据目录',
                        'warning'
                    );
                }
            } catch (e) {
                console.error('Failed to detect WeChat dir', e);
                if (notify) this.showNotification('自动检测失败，请手动填写微信数据目录', 'warning');
            }
        },

        async setWeChatDir() {
            const path = (this.wechatDir || '').trim();
            if (!path) {
                this.showNotification('请输入微信数据目录路径', 'error');
                return false;
            }

            this.loading = true;
            try {
                const res = await fetch(`${this.apiBase}/wechat/set-dir`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path })
                });

                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    throw new Error(data.detail || data.message || '设置微信目录失败');
                }

                if (data && data.path) this.wechatDir = data.path;
                this.showNotification('微信目录已保存', 'success');

                await this.refreshWeChatConfig(false);
                if (this.hasKey) {
                    await this.loadContacts();
                }

                return true;
            } catch (e) {
                this.showNotification(e.message || '设置微信目录失败', 'error');
                return false;
            } finally {
                this.loading = false;
            }
        },

        async extractKey() {
            this.loading = true;
            try {
                const res = await fetch(`${this.apiBase}/wechat/key/extract`, { method: 'POST' });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    throw new Error(data.detail || data.message || '获取密钥失败');
                }

                this.hasKey = true;
                this.showNotification('密钥已获取', 'success');

                if (this.wechatDir) {
                    await this.loadContacts();
                }
            } catch (e) {
                this.showNotification(e.message || '获取密钥失败', 'error');
            } finally {
                this.loading = false;
            }
        },

        async saveSettings() {
            // Only persist WeChat dir for now
            if ((this.wechatDir || '').trim()) {
                const ok = await this.setWeChatDir();
                if (ok) this.showSettings = false;
                return;
            }
            this.showSettings = false;
        },
        
        async checkWeChatStatus() {
            try {
                const res = await fetch(`${this.apiBase}/wechat/status`);
                const data = await res.json();
                return data.running;
            } catch (e) {
                return false;
            }
        },
        
        // Contact methods
        async loadContacts() {
            if (!this.wechatDir) {
                this.contacts = [];
                this.chatrooms = [];
                this.showNotification('请先在设置中填写微信数据目录', 'warning');
                return;
            }
            if (!this.hasKey) {
                this.contacts = [];
                this.chatrooms = [];
                this.showNotification('请先获取解密密钥（设置 → 重新获取）', 'warning');
                return;
            }
            if (this.accounts.length > 1 && !this.activeAccount) {
                this.contacts = [];
                this.chatrooms = [];
                this.showNotification('请先在设置中选择微信账号', 'warning');
                return;
            }

            const makeAvatar = (seed, label) => {
                const text = (label || seed || '?').toString().trim();
                const ch = text ? text[0] : '?';
                let hash = 0;
                const s = (seed || text).toString();
                for (let i = 0; i < s.length; i++) {
                    hash = ((hash << 5) - hash) + s.charCodeAt(i);
                    hash |= 0;
                }
                const colors = ['#16a34a', '#0ea5e9', '#f97316', '#a855f7', '#ef4444', '#64748b'];
                const bg = colors[Math.abs(hash) % colors.length];
                const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="12" fill="${bg}"/>
  <text x="32" y="40" text-anchor="middle" font-family="ui-sans-serif, system-ui" font-size="28" fill="#fff">${ch}</text>
</svg>`;
                return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
            };

            this.loading = true;
            try {
                const [contactsRes, chatroomsRes, extractedRes] = await Promise.all([
                    fetch(`${this.apiBase}/contacts/`),
                    fetch(`${this.apiBase}/contacts/chatrooms`),
                    fetch(`${this.apiBase}/contacts/extracted`)
                ]);

                if (contactsRes.ok) {
                    const data = await contactsRes.json();
                    const list = (data && data.contacts) ? data.contacts : [];
                    this.contacts = list.map(c => {
                        const name = c.remark || c.nickname || c.alias || c.username || c.id;
                        return {
                            ...c,
                            name,
                            type: 'individual',
                            avatar: makeAvatar(c.id, name)
                        };
                    });
                } else {
                    const err = await contactsRes.json().catch(() => ({}));
                    this.contacts = [];
                    this.showNotification(err.detail || '加载联系人失败', 'error');
                }

                if (chatroomsRes.ok) {
                    const data = await chatroomsRes.json();
                    const list = (data && data.chatrooms) ? data.chatrooms : [];
                    this.chatrooms = list.map(c => {
                        const id = c.id || c.name;
                        const name = c.nickname || c.name || id;
                        return {
                            ...c,
                            id,
                            name,
                            type: 'group',
                            avatar: makeAvatar(id, name)
                        };
                    });
                } else {
                    this.chatrooms = [];
                }

                if (extractedRes.ok) {
                    const data = await extractedRes.json();
                    this.hiddenContacts = (data && data.contacts) ? data.contacts : [];
                } else {
                    this.hiddenContacts = [];
                }
            } catch (e) {
                this.error = '加载联系人失败: ' + e.message;
                this.showNotification('加载联系人失败', 'error');
            } finally {
                this.loading = false;
            }
        },
        
        async loadMessages(contactId) {
            const contact = this.allContacts.find(c => c.id === contactId);
            if (!contact) return;
            
            this.currentContact = contact;
            this.loading = true;
            try {
                const res = await fetch(`${this.apiBase}/mode-a/messages/${contactId}`);
                if (!res.ok) throw new Error('加载消息失败');
                this.messages = await res.json();
            } catch (e) {
                this.error = '加载消息失败';
                this.showNotification('加载消息失败', 'error');
            } finally {
                this.loading = false;
            }
        },

        // Mode A methods
        async extractChats() {
            if (this.selectedIds.length === 0) {
                this.showNotification('请先选择联系人', 'error');
                return;
            }
            this.loading = true;
            try {
                const res = await fetch(`${this.apiBase}/mode-a/extract`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({contact_ids: [...this.selectedIds]})
                });
                if (!res.ok) {
                    const msg = await this.readApiError(res, '提取失败');
                    throw new Error(msg);
                }
                const data = await res.json();
                this.showNotification(`成功提取 ${data.total_extracted || 0} 条消息`, 'success');
                await this.loadContacts(); // Refresh to show updated status if needed
            } catch (e) {
                this.error = '提取失败: ' + e.message;
                this.showNotification(e.message || '提取失败', 'error');
            } finally {
                this.loading = false;
            }
        },
        
        // Mode B methods
        async hideChats() {
            // Check preflight first
            try {
                const preflightRes = await fetch(`${this.apiBase}/mode-b/preflight`);
                const preflight = await preflightRes.json();
                if (!preflight.all_passed) {
                    const failedChecks = Object.entries(preflight.checks)
                        .filter(([k,v]) => !v).map(([k]) => k).join(', ');
                    this.showNotification('预检查失败: ' + failedChecks, 'error');
                    return;
                }
                
                // Proceed with hide (Not explicitly bound to a button in the provided HTML, but implementing for completeness)
                // Assuming there's an endpoint for hiding
                /* 
                const res = await fetch(`${this.apiBase}/mode-b/hide`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({contact_ids: [...this.selectedIds]})
                });
                // ... handle response
                */
            } catch (e) {
                this.showNotification('操作失败: ' + e.message, 'error');
            }
        },
        
        async restoreChats() {
            if (this.selectedIds.length === 0) {
                this.showNotification('请先选择联系人', 'error');
                return;
            }
            this.loading = true;
            try {
                let restoredTotal = 0;
                for (const id of this.selectedIds) {
                    const res = await fetch(`${this.apiBase}/mode-b/restore`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({contact_id: id})
                    });
                    if (!res.ok) {
                        const msg = await this.readApiError(res, '还原失败');
                        throw new Error(msg);
                    }
                    const data = await res.json().catch(() => ({}));
                    restoredTotal += Number(data.restored || 0);
                }
                this.showNotification(`聊天记录还原成功（共 ${restoredTotal} 条）`, 'success');
                await this.loadContacts();
            } catch (e) {
                this.showNotification('还原失败: ' + (e.message || ''), 'error');
            } finally {
                this.loading = false;
            }
        },
        
        // Search
        async search() {
            if (!this.searchQuery.trim()) {
                this.searchResults = [];
                return;
            }
            try {
                const res = await fetch(`${this.apiBase}/search/?q=${encodeURIComponent(this.searchQuery)}`);
                if (res.ok) {
                    this.searchResults = await res.json();
                }
            } catch (e) {
                console.error('Search failed', e);
            }
        },
        
        // Export
        async exportChats() {
            if (this.selectedIds.length === 0) {
                this.showNotification('请先选择联系人', 'error');
                return;
            }
            try {
                for (const id of this.selectedIds) {
                    window.open(`${this.apiBase}/export/${id}/download?format=txt`, '_blank');
                }
                this.showNotification('导出请求已发送', 'success');
            } catch (e) {
                this.showNotification('导出失败', 'error');
            }
        },
        
        // UI Helpers
        async readApiError(res, fallbackMessage) {
            try {
                const data = await res.json();
                return data?.detail || data?.message || fallbackMessage;
            } catch (e) {
                return fallbackMessage;
            }
        },

        showNotification(message, type = 'info') {
            this.toastMessage = message;
            this.toastType = type;
            this.showToast = true;
            setTimeout(() => {
                this.showToast = false;
            }, 3000);
        },
        
        toggleContact(id) {
            if (this.selectedIds.includes(id)) {
                this.selectedIds = this.selectedIds.filter(i => i !== id);
            } else {
                this.selectedIds.push(id);
            }
            
            // If only one selected, show its chat
            if (this.selectedIds.length === 1) {
                this.loadMessages(this.selectedIds[0]);
            } else {
                this.messages = [];
                this.currentContact = null;
            }
        },
        
        selectAll() {
            this.selectedIds = this.filteredContacts.map(c => c.id);
        },
        
        deselectAll() {
            this.selectedIds = [];
            this.messages = [];
            this.currentContact = null;
        },
        
        async switchMode(newMode) {
            if (newMode === this.mode) return;
            
            if (newMode === 'convenient') {
                this.pendingMode = newMode;
                this.showRiskWarning = true;
            } else {
                this.mode = newMode;
                this.showNotification('已切换至安全模式', 'info');
            }
        },
        
        confirmModeB() {
            this.mode = 'convenient';
            this.showRiskWarning = false;
            this.showNotification('已切换至便捷模式', 'warning');
            // Potentially trigger preflight check here
            this.hideChats(); // Check preflight when entering mode B? Or just when performing action?
            // For now, just switch UI mode.
        },
        
        cancelModeB() {
            this.showRiskWarning = false;
            this.pendingMode = null;
        },
        
        // Getters
        get allContacts() {
            // Combine contacts and chatrooms
            // Ensure they have a 'type' property if not present
            const individuals = this.contacts.map(c => ({...c, type: c.type || 'individual'}));
            const groups = this.chatrooms.map(c => ({...c, type: c.type || 'group'}));
            return [...individuals, ...groups];
        },

        get filteredContacts() {
            let list = this.allContacts;
            
            // If search query exists, use it (client-side filtering for responsiveness, 
            // or use searchResults if we want server-side search)
            // The prompt implemented server-side search: async search().
            // But the UI also has a getter for filteredContacts.
            // Let's use client-side filtering for the main list if we have data, 
            // but if we have searchResults from server, maybe use that?
            // For now, let's stick to client-side filtering of loaded contacts for speed,
            // as loadContacts fetches everything.
            
            const q = (this.searchQuery || '').trim().toLowerCase();
            if (!q) return list;

            return list.filter(c => {
                const fields = [
                    c.name,
                    c.remark,
                    c.nickname,
                    c.alias,
                    c.username,
                    c.id
                ].filter(Boolean);
                return fields.join(' ').toLowerCase().includes(q);
            });
        },
        
        get selectedCount() {
            return this.selectedIds.length;
        },
        
        get isAllSelected() {
            return this.filteredContacts.length > 0 && 
                   this.filteredContacts.every(c => this.selectedIds.includes(c.id));
        }
    }))
});
