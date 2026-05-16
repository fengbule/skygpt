// SkyGPT Main JavaScript
document.addEventListener('DOMContentLoaded', function() {
    const registrationForm = document.getElementById('registrationForm');
    const registrationModeSelect = document.getElementById('registrationMode');
    const phoneModeSection = document.getElementById('phoneModeSection');
    const proxySourceSelect = document.getElementById('proxySource');
    const proxyManualSection = document.getElementById('proxyManualSection');
    const proxySubscriptionSection = document.getElementById('proxySubscriptionSection');
    const testProxyBtn = document.getElementById('testProxyBtn');
    const proxyTestResult = document.getElementById('proxyTestResult');
    const taskResult = document.getElementById('taskResult');

    async function loadSavedSmsDefaults() {
        try {
            const response = await fetch('/api/settings/sms/default');
            const data = await response.json();
            if (!data.success || !data.item) {
                return;
            }
            const item = data.item;
            const config = item.config || {};
            const smsProviderSelect = document.getElementById('smsProvider');
            if (smsProviderSelect && item.provider) {
                smsProviderSelect.value = item.provider;
            }
            const mapping = {
                phoneCountry: config.default_country,
                smsServiceCode: config.default_service,
                smsOperator: config.operator,
                smsBaseUrl: config.base_url,
                smsPollInterval: config.poll_interval,
                smsMaxWait: config.max_wait,
                smsMaxPrice: config.max_price,
            };
            Object.entries(mapping).forEach(([id, value]) => {
                const el = document.getElementById(id);
                if (el && !el.value && value !== null && value !== undefined && value !== '') {
                    el.value = value;
                }
            });
        } catch (error) {
            console.warn('加载已保存短信设置失败:', error);
        }
    }

    function syncRegistrationMode() {
        if (!registrationModeSelect) {
            return;
        }
        const mode = registrationModeSelect.value;
        const emailInput = document.getElementById('email');
        const emailLabel = document.querySelector('label[for="email"]');
        const isPhone = mode === 'phone';

        if (phoneModeSection) {
            phoneModeSection.style.display = isPhone ? 'block' : 'none';
        }
        if (emailInput) {
            emailInput.required = !isPhone;
            emailInput.placeholder = isPhone ? '手机号模式可留空' : 'your.email@example.com';
        }
        if (emailLabel) {
            emailLabel.textContent = isPhone ? '邮箱地址（可选，占位/后续补绑）' : '邮箱地址 *';
        }
    }

    if (registrationModeSelect) {
        registrationModeSelect.addEventListener('change', syncRegistrationMode);
    }
    syncRegistrationMode();
    loadSavedSmsDefaults();

    if (proxySourceSelect) {
        proxySourceSelect.addEventListener('change', function() {
            const value = this.value;
            if (proxyManualSection) {
                proxyManualSection.style.display = value === 'manual' ? 'block' : 'none';
            }
            if (proxySubscriptionSection) {
                proxySubscriptionSection.style.display = value === 'subscription' ? 'block' : 'none';
            }
        });
    }

    if (testProxyBtn) {
        testProxyBtn.addEventListener('click', async function() {
        const proxyUrl = document.getElementById('proxyManual').value;
        if (!proxyUrl) {
            proxyTestResult.innerHTML = '<div class="error">请输入代理地址</div>';
            return;
        }

        proxyTestResult.innerHTML = '<div class="test-result">测试中...</div>';

        try {
            const response = await fetch('/api/proxies/add', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({url: proxyUrl, type: 'manual', source: 'manual'})
            });

            const data = await response.json();

            if (data.success) {
                proxyTestResult.innerHTML = `<div class="test-result success">代理可用 -延迟: ${data.latency.toFixed(2)}s</div>`;
            } else {
                proxyTestResult.innerHTML = `<div class="test-result error">${data.message || data.error}</div>`;
            }
        } catch (error) {
            proxyTestResult.innerHTML = `<div class="test-result error">测试失败: ${error.message}</div>`;
        }
        });
    }

    if (registrationForm) {
        registrationForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const registrationMode = registrationModeSelect?.value || 'email';
        const email = document.getElementById('email').value;
        const name = document.getElementById('name').value;
        const birthday = document.getElementById('birthday').value;
        const phoneCountry = document.getElementById('phoneCountry')?.value || '';
        const smsServiceCode = document.getElementById('smsServiceCode')?.value || '';
        const smsOperator = document.getElementById('smsOperator')?.value || '';
        const smsProvider = document.getElementById('smsProvider')?.value || 'hero_sms';
        const smsApiKey = document.getElementById('smsApiKey')?.value || '';
        const smsBaseUrl = document.getElementById('smsBaseUrl')?.value || '';
        const smsPollIntervalRaw = document.getElementById('smsPollInterval')?.value || '';
        const smsMaxWaitRaw = document.getElementById('smsMaxWait')?.value || '';
        const smsMaxPriceRaw = document.getElementById('smsMaxPrice')?.value || '';
        const smsPollInterval = smsPollIntervalRaw ? parseInt(smsPollIntervalRaw, 10) : null;
        const smsMaxWait = smsMaxWaitRaw ? parseInt(smsMaxWaitRaw, 10) : null;
        const smsMaxPrice = smsMaxPriceRaw ? parseFloat(smsMaxPriceRaw) : null;
        const proxySource = proxySourceSelect.value;
        let proxy = null;

        if (proxySource === 'manual') {
            proxy = document.getElementById('proxyManual').value;
        }

        taskResult.innerHTML = '<div class="test-result">创建任务中...</div>';

        try {
            const response = await fetch('/api/tasks/create', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    registration_mode: registrationMode,
                    email,
                    name,
                    birthday,
                    proxy,
                    phone_country: phoneCountry,
                    sms_service_code: smsServiceCode,
                    sms_operator: smsOperator,
                    sms_provider: smsProvider,
                    sms_api_key: smsApiKey,
                    sms_base_url: smsBaseUrl,
                    sms_poll_interval: Number.isFinite(smsPollInterval) ? smsPollInterval : null,
                    sms_max_wait: Number.isFinite(smsMaxWait) ? smsMaxWait : null,
                    sms_max_price: Number.isFinite(smsMaxPrice) ? smsMaxPrice : null,
                })
            });

            const data = await response.json();

            if (data.success) {
                taskResult.innerHTML = `<div class="test-result success">任务已创建！任务ID: ${data.task.id}<br>请前往<a href="/tasks">任务页面</a>查看进度</div>`;
                registrationForm.reset();
                syncRegistrationMode();
            } else {
                taskResult.innerHTML = `<div class="test-result error">创建失败: ${data.error}</div>`;
            }
        } catch (error) {
            taskResult.innerHTML = `<div class="test-result error">请求失败: ${error.message}</div>`;
        }
        });
    }

    const importSubscriptionBtn = document.getElementById('importSubscriptionBtn');
    if (importSubscriptionBtn) {
        importSubscriptionBtn.addEventListener('click', async function() {
            const subUrl = document.getElementById('subscriptionUrl').value;
            if (!subUrl) {
                document.getElementById('subscriptionNodes').innerHTML = '<div class="error">请输入订阅链接</div>';
                return;
            }

            document.getElementById('subscriptionNodes').innerHTML = '<div class="test-result">导入中...</div>';

            try {
                const response = await fetch('/api/proxies/import_subscription', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: subUrl})
                });

                const data = await response.json();

                if (data.success) {
                    document.getElementById('subscriptionNodes').innerHTML = `<div class="test-result success">成功导入 ${data.count} 个代理节点</div>`;
                } else {
                    document.getElementById('subscriptionNodes').innerHTML = `<div class="test-result error">${data.error}</div>`;
                }
            } catch (error) {
                document.getElementById('subscriptionNodes').innerHTML = `<div class="test-result error">导入失败: ${error.message}</div>`;
            }
        });
    }
});