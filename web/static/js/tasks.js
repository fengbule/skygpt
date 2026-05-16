// SkyGPT Tasks JavaScript - Real-time Progress Visualization
let socket = null;
let currentTaskId = null;

const REGISTRATION_STEPS = [
    {id: 1, name: "获取 Providers"},
    {id: 2, name: "获取 CSRF Token"},
    {id: 3, name: "发起 OAuth signin"},
    {id: 4, name: "跟随 authorize URL"},
    {id: 5, name: "等待邮箱验证码"},
    {id: 6, name: "获取 Sentinel Token"},
    {id: 7, name: "提交邮箱验证码"},
    {id: 8, name: "等待手机验证（可选）"},
    {id: 9, name: "获取 OAuth Sentinel"},
    {id: 10, name: "创建账号"},
    {id: 11, name: "OAuth 回调"},
    {id: 12, name: "生成 CPA 文件"}
];

document.addEventListener('DOMContentLoaded', function() {
    loadTasks();
    initWebSocket();
    
    document.getElementById('refreshTasksBtn').addEventListener('click', loadTasks);
    document.getElementById('statusFilter').addEventListener('change', loadTasks);
    document.getElementById('cancelTaskBtn').addEventListener('click', cancelCurrentTask);
    
    document.getElementById('otpForm').addEventListener('submit', submitOTP);
    document.getElementById('cancelOtpBtn').addEventListener('click', function() {
        cancelCurrentTask();
        hideOTPModal();
    });
});

function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}`;
    
    socket = io(wsUrl, {
        transports: ['websocket'],
        upgrade: false
    });
    
    socket.on('connect', function() {
        console.log('WebSocket connected');
        addSystemLog('WebSocket 连接成功');
    });
    
    socket.on('disconnect', function() {
        console.log('WebSocket disconnected');
        addSystemLog('WebSocket 断开连接', 'WARNING');
    });
    
    socket.on('task_started', function(data) {
        addSystemLog(`任务 ${data.task_id} 已启动`);
        if (currentTaskId === data.task_id) {
            addLogEntry(data.message, 'INFO');
        }
        loadTasks();
    });
    
    socket.on('step_update', function(data) {
        console.log('Step update:', data);
        if (currentTaskId === data.task_id) {
            updateStepProgress(data.step_id, data.status, data.step_name);
            addLogEntry(`步骤 ${data.step_id}/${REGISTRATION_STEPS.length}: ${data.step_name} - ${data.status}`, 
                data.status === 'completed' ? 'SUCCESS' : 
                data.status === 'failed' ? 'ERROR' : 'INFO');
        }
        loadTasks();
    });
    
    socket.on('log_update', function(data) {
        if (currentTaskId === data.task_id) {
            addLogEntry(data.log.message, data.log.level);
        }
    });
    
    socket.on('waiting_for_input', function(data) {
        console.log('Waiting for input:', data);
        if (currentTaskId === data.task_id) {
            showOTPModal(data.input_type);
            addLogEntry(data.message, 'WARNING');
        }
        loadTasks();
    });
    
    socket.on('task_completed', function(data) {
        addSystemLog(`任务 ${data.task_id} 完成: ${data.email}`, 'SUCCESS');
        if (currentTaskId === data.task_id) {
            addLogEntry('注册成功！账号 ID: ' + data.account_id, 'SUCCESS');
            document.getElementById('taskStatus').textContent = '成功';
            document.getElementById('cancelTaskBtn').disabled = true;
        }
        loadTasks();
    });
    
    socket.on('task_failed', function(data) {
        addSystemLog(`任务 ${data.task_id} 失败: ${data.error}`, 'ERROR');
        if (currentTaskId === data.task_id) {
            addLogEntry('注册失败: ' + data.error, 'ERROR');
            document.getElementById('taskStatus').textContent = '失败';
        }
        loadTasks();
    });
    
    socket.on('task_cancelled', function(data) {
        addSystemLog(`任务 ${data.task_id} 已取消`, 'WARNING');
        if (currentTaskId === data.task_id) {
            addLogEntry('用户取消了任务', 'WARNING');
            document.getElementById('taskStatus').textContent = '已取消';
            hideOTPModal();
        }
        loadTasks();
    });
}

function addSystemLog(message, level = 'INFO') {
    const logsContainer = document.getElementById('logsContainer');
    const logDiv = document.createElement('div');
    logDiv.className = `log-entry ${level}`;
    logDiv.innerHTML = `<span class="log-time">[${new Date().toLocaleTimeString()}]</span> ${message}`;
    logsContainer.appendChild(logDiv);
    logsContainer.scrollTop = logsContainer.scrollHeight;
}

function addLogEntry(message, level = 'INFO') {
    const logsContainer = document.getElementById('logsContainer');
    const logDiv = document.createElement('div');
    logDiv.className = `log-entry ${level}`;
    
    const timestamp = new Date().toLocaleTimeString();
    logDiv.innerHTML = `<span class="log-time">[${timestamp}]</span> ${message}`;
    
    logsContainer.appendChild(logDiv);
    logsContainer.scrollTop = logsContainer.scrollHeight;
}

function loadTasks() {
    const status = document.getElementById('statusFilter').value;
    
    fetch(`/api/tasks/list?status=${status}`)
        .then(r => r.json())
        .then(data => {
            if (data.tasks && data.tasks.length > 0) {
                let html = '<table><tr><th>ID</th><th>邮箱</th><th>状态</th><th>代理</th><th>创建时间</th><th>操作</th></tr>';
                data.tasks.forEach(t => {
                    const statusClass = getStatusClass(t.status);
                    html += `<tr>
                        <td>${t.id}</td>
                        <td>${t.email}</td>
                        <td><span class="status-badge ${statusClass}">${getStatusText(t.status)}</span></td>
                        <td>${t.proxy || '无'}</td>
                        <td>${t.created_at || '-'}</td>
                        <td>
                            <button onclick="viewTask(${t.id}, '${t.email}')">查看详情</button>
                            ${t.status !== 'success' && t.status !== 'failed' && t.status !== 'cancelled' ? 
                                `<button onclick="cancelTask(${t.id})">取消</button>` : ''}
                        </td>
                    </tr>`;
                });
                html += '</table>';
                document.getElementById('tasksTable').innerHTML = html;
            } else {
                document.getElementById('tasksTable').innerHTML = '<p style="text-align:center; padding: 40px; color: #7f8c8d;">暂无任务，请前往<a href="/">注册页面</a>创建新任务</p>';
            }
        })
        .catch(err => {
            console.error('Load tasks error:', err);
            document.getElementById('tasksTable').innerHTML = '<p class="error">加载任务失败</p>';
        });
}

function getStatusClass(status) {
    const classes = {
        'pending': 'status-pending',
        'running': 'status-running',
        'waiting_for_input': 'status-waiting',
        'success': 'status-success',
        'failed': 'status-failed',
        'cancelled': 'status-cancelled'
    };
    return classes[status] || 'status-pending';
}

function getStatusText(status) {
    const texts = {
        'pending': '等待中',
        'running': '进行中',
        'waiting_for_input': '等待输入',
        'success': '成功',
        'failed': '失败',
        'cancelled': '已取消'
    };
    return texts[status] || status;
}

function viewTask(taskId, email) {
    currentTaskId = taskId;
    
    document.getElementById('taskDetailSection').style.display = 'block';
    document.getElementById('taskEmail').textContent = email;
    
    fetch(`/api/tasks/${taskId}`)
        .then(r => r.json())
        .then(data => {
            if (data.task) {
                document.getElementById('taskStatus').textContent = getStatusText(data.task.status);
                renderProgressBar();
                
                if (data.task.status === 'running' || data.task.status === 'waiting_for_input') {
                    document.getElementById('cancelTaskBtn').disabled = false;
                } else {
                    document.getElementById('cancelTaskBtn').disabled = true;
                }
                
                socket.emit('subscribe_task', {task_id: taskId});
            }
        });
    
    document.getElementById('logsContainer').innerHTML = '';
    addSystemLog(`正在加载任务 ${taskId} 的实时日志...`);
}

function renderProgressBar() {
    const progressBar = document.getElementById('progressBar');
    progressBar.innerHTML = '';
    
    REGISTRATION_STEPS.forEach(step => {
        const stepDiv = document.createElement('div');
        stepDiv.className = 'step-item pending';
        stepDiv.id = `step-${step.id}`;
        
        stepDiv.innerHTML = `
            <div class="step-circle">${step.id}</div>
            <div class="step-name">${step.name}</div>
        `;
        
        progressBar.appendChild(stepDiv);
    });
}

function updateStepProgress(stepId, status, stepName) {
    const stepElement = document.getElementById(`step-${stepId}`);
    if (stepElement) {
        stepElement.className = `step-item ${status}`;
        
        if (status === 'running') {
            stepElement.querySelector('.step-circle').innerHTML = '⟳';
        } else if (status === 'completed') {
            stepElement.querySelector('.step-circle').innerHTML = '✓';
        } else if (status === 'failed') {
            stepElement.querySelector('.step-circle').innerHTML = '✗';
        } else if (status === 'waiting') {
            stepElement.querySelector('.step-circle').innerHTML = '?';
        } else {
            stepElement.querySelector('.step-circle').innerHTML = stepId;
        }
    }
}

function cancelCurrentTask() {
    if (!currentTaskId) return;
    
    if (confirm('确定要取消当前任务吗？')) {
        cancelTask(currentTaskId);
    }
}

function cancelTask(taskId) {
    fetch(`/api/tasks/${taskId}/cancel`, {method: 'POST'})
        .then(r => r.json())
        .then(d => {
            if (d.success) {
                addSystemLog('任务已取消', 'WARNING');
                loadTasks();
            } else {
                alert('取消失败: ' + d.error);
            }
        })
        .catch(err => {
            console.error('Cancel error:', err);
            alert('取消失败');
        });
}

function showOTPModal(inputType) {
    const modal = document.getElementById('otpModal');
    const promptText = document.getElementById('otpPromptText');
    const emailOtpGroup = document.getElementById('emailOtpGroup');
    const phoneOtpGroup = document.getElementById('phoneOtpGroup');
    
    if (inputType === 'email_otp') {
        promptText.textContent = '请检查邮箱，输入收到的 6 位验证码';
        emailOtpGroup.style.display = 'block';
        phoneOtpGroup.style.display = 'none';
        document.getElementById('emailOtpInput').focus();
    } else if (inputType === 'phone_otp') {
        promptText.textContent = '请输入手机号码和收到的验证码';
        emailOtpGroup.style.display = 'none';
        phoneOtpGroup.style.display = 'block';
        document.getElementById('phoneNumberInput').focus();
    }
    
    modal.style.display = 'flex';
}

function hideOTPModal() {
    document.getElementById('otpModal').style.display = 'none';
    document.getElementById('emailOtpInput').value = '';
    document.getElementById('phoneOtpInput').value = '';
    document.getElementById('phoneNumberInput').value = '';
}

function submitOTP(e) {
    e.preventDefault();
    
    const emailOtp = document.getElementById('emailOtpInput').value;
    const phoneOtp = document.getElementById('phoneOtpInput').value;
    const phoneNumber = document.getElementById('phoneNumberInput').value;
    
    let otpType = null;
    let otpCode = null;
    
    if (emailOtp) {
        otpType = 'email_otp';
        otpCode = emailOtp;
    } else if (phoneOtp && phoneNumber) {
        otpType = 'phone_otp';
        otpCode = phoneOtp;
    } else {
        alert('请输入验证码');
        return;
    }
    
    fetch(`/api/tasks/${currentTaskId}/submit_otp`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            otp_type: otpType,
            otp_code: otpCode,
            phone_number: phoneNumber
        })
    })
    .then(r => r.json())
    .then(d => {
        if (d.success) {
            addSystemLog('验证码已提交', 'SUCCESS');
            hideOTPModal();
        } else {
            alert('提交失败: ' + d.error);
        }
    })
    .catch(err => {
        console.error('Submit OTP error:', err);
        alert('提交失败');
    });
}