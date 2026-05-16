// SkyGPT Proxies JavaScript
document.addEventListener('DOMContentLoaded', loadProxies);

function loadProxies() {
    fetch('/api/proxies/list')
        .then(r => r.json())
        .then(data => {
            if (data.proxies && data.proxies.length > 0) {
                let html = '<table><tr><th>ID</th><th>代理地址</th><th>类型</th><th>状态</th><th>延迟</th><th>操作</th></tr>';
                data.proxies.forEach(p => {
                    const statusText = p.available === 1 ? '可用' : '不可用';
                    const statusClass = p.available === 1 ? 'success' : 'error';
                    html += `<tr>
                        <td>${p.id}</td>
                        <td>${p.url}</td>
                        <td>${p.type}</td>
                        <td class="test-result ${statusClass}">${statusText}</td>
                        <td>${p.latency ? p.latency.toFixed(2) + 's' : '-'}</td>
                        <td>
                            <button onclick="testProxy(${p.id})">测试</button>
                            <button onclick="deleteProxy(${p.id})">删除</button>
                        </td>
                    </tr>`;
                });
                html += '</table>';
                document.getElementById('proxiesTable').innerHTML = html;
            } else {
                document.getElementById('proxiesTable').innerHTML = '<p>暂无代理</p>';
            }
        });
}

document.getElementById('testAllBtn').addEventListener('click', function() {
    fetch('/api/proxies/test_all', {method: 'POST'})
        .then(r => r.json())
        .then(d => {
            if (d.success) {
                alert('测试完成');
                loadProxies();
            }
        });
});

document.getElementById('addProxyForm').addEventListener('submit', function(e) {
    e.preventDefault();
    const url = document.getElementById('proxyUrl').value;
    fetch('/api/proxies/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url, type: 'manual', source: 'manual'})
    }).then(r => r.json())
    .then(d => {
        if (d.success) {
            alert('添加成功');
            loadProxies();
        } else {
            alert('添加失败: ' + d.error);
        }
    });
});

function testProxy(id) {
    fetch(`/api/proxies/${id}/test`, {method: 'POST'})
        .then(r => r.json())
        .then(d => {
            if (d.success) {
                alert('测试完成');
                loadProxies();
            }
        });
}

function deleteProxy(id) {
    fetch(`/api/proxies/${id}`, {method: 'DELETE'})
        .then(r => r.json())
        .then(d => {
            if (d.success) {
                loadProxies();
            }
        });
}