document.addEventListener('DOMContentLoaded', function () {
    const container = document.getElementById('smsSettingsContainer');
    const statusBox = document.getElementById('settingsStatus');

    function showStatus(message, type = 'success') {
        if (!statusBox) return;
        statusBox.className = `test-result ${type}`;
        statusBox.textContent = message;
        statusBox.style.display = 'block';
    }

    function buildProviderForm(item) {
        const config = item.config || {};
        return `
            <div class="provider-card">
                <div class="provider-card-header">
                    <div>
                        <h3>${item.display_name || item.provider}</h3>
                        <p>${item.provider}</p>
                    </div>
                    <label class="inline-check"><input type="checkbox" data-field="enabled" ${item.enabled ? 'checked' : ''}> 启用</label>
                </div>
                <div class="provider-grid">
                    <label>显示名称<input type="text" data-field="display_name" value="${item.display_name || ''}"></label>
                    <label>设为默认<input type="checkbox" data-field="is_default" ${item.is_default ? 'checked' : ''}></label>
                    <label>API Key<input type="password" data-config="api_key" value="${config.api_key || ''}" placeholder="不填则回退环境变量"></label>
                    <label>Base URL<input type="text" data-config="base_url" value="${config.base_url || ''}"></label>
                    <label>默认国家<input type="text" data-config="default_country" value="${config.default_country || ''}"></label>
                    <label>默认服务<input type="text" data-config="default_service" value="${config.default_service || ''}"></label>
                    <label>运营商<input type="text" data-config="operator" value="${config.operator || ''}"></label>
                    <label>轮询间隔<input type="number" data-config="poll_interval" value="${config.poll_interval ?? ''}"></label>
                    <label>最大等待<input type="number" data-config="max_wait" value="${config.max_wait ?? ''}"></label>
                    <label>最高价格<input type="number" step="0.01" data-config="max_price" value="${config.max_price ?? ''}"></label>
                    <label>自动选最优国家<input type="checkbox" data-config="auto_select_best_country" ${config.auto_select_best_country ? 'checked' : ''}></label>
                    <label>最小库存<input type="number" data-config="best_country_min_stock" value="${config.best_country_min_stock ?? 20}"></label>
                    <label>最高价格限制<input type="number" step="0.01" data-config="best_country_max_price" value="${config.best_country_max_price ?? 0}"></label>
                </div>
                <div class="provider-actions">
                    <button class="btn-primary" data-action="save">保存</button>
                    <button class="btn-test" data-action="test">测试连接</button>
                </div>
            </div>
        `;
    }

    function collectPayload(card, provider) {
        const payload = {
            provider,
            display_name: card.querySelector('[data-field="display_name"]').value.trim(),
            enabled: card.querySelector('[data-field="enabled"]').checked,
            is_default: card.querySelector('[data-field="is_default"]').checked,
            config: {},
        };
        card.querySelectorAll('[data-config]').forEach(el => {
            const key = el.dataset.config;
            if (el.type === 'checkbox') {
                payload.config[key] = el.checked;
            } else {
                payload.config[key] = el.value;
            }
        });
        return payload;
    }

    async function loadSettings() {
        const response = await fetch('/api/settings/sms');
        const data = await response.json();
        if (!data.success) {
            showStatus(data.error || '加载设置失败', 'error');
            return;
        }
        container.innerHTML = data.providers.map(buildProviderForm).join('');
        bindActions();
    }

    function bindActions() {
        container.querySelectorAll('.provider-card').forEach((card, index) => {
            const provider = ['hero_sms', 'sms_activate', 'api_cc'][index] || card.querySelector('p')?.textContent?.trim();
            card.querySelector('[data-action="save"]').addEventListener('click', async () => {
                const payload = collectPayload(card, provider);
                const response = await fetch(`/api/settings/sms/${provider}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload),
                });
                const data = await response.json();
                if (data.success) {
                    showStatus(`${provider} 设置已保存`, 'success');
                    loadSettings();
                } else {
                    showStatus(data.error || '保存失败', 'error');
                }
            });

            card.querySelector('[data-action="test"]').addEventListener('click', async () => {
                const payload = collectPayload(card, provider);
                const response = await fetch(`/api/settings/sms/${provider}/test`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload),
                });
                const data = await response.json();
                if (data.success) {
                    showStatus(`${provider} 测试成功`, 'success');
                } else {
                    showStatus(data.error || '测试失败', 'error');
                }
            });
        });
    }

    loadSettings();
});