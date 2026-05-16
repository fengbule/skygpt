// SkyGPT Main JavaScript
document.addEventListener('DOMContentLoaded', function() {
    const registrationForm = document.getElementById('registrationForm');
    const proxySourceSelect = document.getElementById('proxySource');
    const proxyManualSection = document.getElementById('proxyManualSection');
    const proxySubscriptionSection = document.getElementById('proxySubscriptionSection');
    const testProxyBtn = document.getElementById('testProxyBtn');
    const proxyTestResult = document.getElementById('proxyTestResult');
    const taskResult = document.getElementById('taskResult');

    proxySourceSelect.addEventListener('change', function() {
        const value = this.value;
        proxyManualSection.style.display = value === 'manual' ? 'block' : 'none';
        proxySubscriptionSection.style.display = value === 'subscription' ? 'block' : 'none';
    });

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

    registrationForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const email = document.getElementById('email').value;
        const name = document.getElementById('name').value;
        const birthday = document.getElementById('birthday').value;
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
                body: JSON.stringify({email, name, birthday, proxy})
            });

            const data = await response.json();

            if (data.success) {
                taskResult.innerHTML = `<div class="test-result success">任务已创建！任务ID: ${data.task.id}<br>请前往<a href="/tasks">任务页面</a>查看进度</div>`;
                registrationForm.reset();
            } else {
                taskResult.innerHTML = `<div class="test-result error">创建失败: ${data.error}</div>`;
            }
        } catch (error) {
            taskResult.innerHTML = `<div class="test-result error">请求失败: ${error.message}</div>`;
        }
    });

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