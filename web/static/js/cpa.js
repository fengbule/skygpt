// SkyGPT CPA JavaScript
document.addEventListener('DOMContentLoaded', loadCPAFiles);

function loadCPAFiles() {
    fetch('/api/cpa/list')
        .then(r => r.json())
        .then(data => {
            if (data.cpa_files && data.cpa_files.length > 0) {
                let html = '<table><tr><th>邮箱</th><th>账号ID</th><th>过期时间</th><th>状态</th><th>操作</th></tr>';
                data.cpa_files.forEach(c => {
                    const status = c.disabled ? '已禁用' : '可用';
                    html += `<tr>
                        <td>${c.email}</td>
                        <td>${c.account_id || '-'}</td>
                        <td>${c.expired || '-'}</td>
                        <td>${status}</td>
                        <td>
                            <a href="/api/cpa/download/${c.cpa_file}" download>下载</a>
                            <button onclick="toggleAccount('${c.email}', ${c.disabled})">${c.disabled ? '启用' : '禁用'}</button>
                        </td>
                    </tr>`;
                });
                html += '</table>';
                document.getElementById('cpaTable').innerHTML = html;
            } else {
                document.getElementById('cpaTable').innerHTML = '<p>暂无CPA文件</p>';
            }
        });
}

document.getElementById('downloadAllBtn').addEventListener('click', function() {
    fetch('/api/cpa/download_batch', {method: 'POST'})
        .then(r => r.blob())
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'cpa_batch.zip';
            a.click();
        });
});

function toggleAccount(email, disabled) {
    const action = disabled ? 'enable' : 'disable';
    fetch(`/api/cpa/${action}/${email}`, {method: 'POST'})
        .then(r => r.json())
        .then(d => {
            if (d.success) {
                loadCPAFiles();
            }
        });
}