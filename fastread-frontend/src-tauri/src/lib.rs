use tauri::{Manager, Emitter, State};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use std::env;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use serde::Serialize;

// Sidecar 子进程句柄，用 Mutex 包裹方便 restart 时杀旧进程
struct SidecarHandle(Mutex<Option<CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // 启动 Sidecar 并把 child handle 存到 state，方便后续 restart_backend_sidecar 使用
            let child = spawn_backend_sidecar(app.handle()).map_err(|e| {
                eprintln!("Sidecar 启动失败: {}", e);
                e
            })?;
            app.manage(SidecarHandle(Mutex::new(Some(child))));

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_install_path_diagnostics,
            restart_backend_sidecar
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

// 启动后端 Sidecar：负责装环境变量、spawn、挂 stdout/stderr/terminated 监听并 emit 给前端。
// 第一次启动 + restart_backend_sidecar 都走这里，保持单一启动路径。
fn spawn_backend_sidecar(app_handle: &tauri::AppHandle) -> Result<CommandChild, String> {
    let exe_path = env::current_exe().map_err(|e| format!("无法获取可执行文件路径: {}", e))?;
    let sidecar_dir = exe_path
        .parent()
        .ok_or("无法获取可执行文件父目录")?
        .to_path_buf();

    // 继承系统环境变量，并注入 FastRead 专用数据根。
    let mut all_env_vars = HashMap::new();
    for (key, value) in env::vars() {
        all_env_vars.insert(key, value);
    }
    let data_root = resolve_data_root(app_handle)?;
    std::fs::create_dir_all(&data_root)
        .map_err(|e| format!("无法创建 FastRead 应用数据目录: {}", e))?;
    all_env_vars.insert(
        "FASTREAD_DATA_ROOT".to_string(),
        data_root.to_string_lossy().to_string(),
    );
    all_env_vars.insert("BACKEND_HOST".to_string(), "127.0.0.1".to_string());

    let mut sidecar_command = app_handle
        .shell()
        .sidecar("FastReadBackend")
        .map_err(|e| format!("找不到 FastReadBackend sidecar: {}", e))?;
    for (key, value) in &all_env_vars {
        sidecar_command = sidecar_command.env(key, value);
    }

    let (mut rx, child) = sidecar_command
        .current_dir(sidecar_dir)
        .spawn()
        .map_err(|e| format!("spawn sidecar 失败: {}", e))?;

    // 异步监听 stdout / stderr / terminated 事件，转发到前端 webview
    let app_handle_for_listener = app_handle.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            // window 句柄每次重新取，允许窗口关闭重开
            let window = app_handle_for_listener.get_webview_window("main");
            match event {
                CommandEvent::Stdout(line) => {
                    let output = String::from_utf8_lossy(&line).to_string();
                    println!("Backend stdout: {}", output);
                    if let Some(w) = window {
                        let _ = w.emit("backend-message", Some(output));
                    }
                }
                CommandEvent::Stderr(line) => {
                    let error = String::from_utf8_lossy(&line).to_string();
                    eprintln!("Backend stderr: {}", error);
                    if let Some(w) = window {
                        let _ = w.emit("backend-error", Some(error));
                    }
                }
                CommandEvent::Terminated(payload) => {
                    println!("Backend terminated with code: {:?}", payload.code);
                    if let Some(w) = window {
                        let _ = w.emit("backend-terminated", Some(payload.code));
                    }
                    break;
                }
                _ => {
                    println!("Backend event: {:?}", event);
                }
            }
        }
    });

    Ok(child)
}

// Production defaults to Tauri's per-user roaming app-data directory. An
// explicit absolute override keeps managed/portable deployments and release
// smoke tests isolated without changing the installation directory.
fn resolve_data_root(app_handle: &tauri::AppHandle) -> Result<PathBuf, String> {
    if let Some(value) = env::var_os("FASTREAD_DATA_ROOT").filter(|value| !value.is_empty()) {
        let path = PathBuf::from(value);
        if !path.is_absolute() {
            return Err("FASTREAD_DATA_ROOT 必须是绝对路径".to_string());
        }
        return Ok(path);
    }

    app_handle
        .path()
        .app_data_dir()
        .map_err(|e| format!("无法获取 FastRead 应用数据目录: {}", e))
}

// 重启 sidecar：杀旧 child，spawn 新 child，回写到 state。
#[tauri::command]
fn restart_backend_sidecar(
    state: State<'_, SidecarHandle>,
    app: tauri::AppHandle,
) -> Result<(), String> {
    // 1. 拿出旧 child 并 kill（kill 失败也继续，可能进程已经退了）
    {
        let mut guard = state.0.lock().map_err(|e| format!("锁 sidecar state 失败: {}", e))?;
        if let Some(child) = guard.take() {
            let _ = child.kill();
        }
    }
    // 2. 重新 spawn
    let new_child = spawn_backend_sidecar(&app)?;
    {
        let mut guard = state.0.lock().map_err(|e| format!("锁 sidecar state 失败: {}", e))?;
        *guard = Some(new_child);
    }
    // 3. emit 一个事件让前端知道已重启
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.emit("backend-restarted", ());
    }
    Ok(())
}

// Keep path characteristics available for on-demand diagnostics. They are not
// startup failures: the bundled backend is verified in paths containing spaces
// and non-ASCII characters, and all mutable data lives under FASTREAD_DATA_ROOT.
#[derive(Serialize, Clone)]
struct InstallPathDiagnostics {
    exe_path: String,
    path_has_non_ascii: bool,
    path_has_space: bool,
    parent_writable: bool,
    platform: String,
}

fn analyze_install_path(exe_path: &Path) -> InstallPathDiagnostics {
    let path_str = exe_path.to_string_lossy().to_string();
    // 不在 ASCII 范围内的字符（中文 / 日文 / 西里尔等都会命中 PyInstaller 路径解析坑）
    let has_non_ascii = path_str.chars().any(|c| !c.is_ascii());
    // 空格本身在 Windows shell 引号场景偶尔出问题，且 macOS path 里也偶尔触发 sidecar 启动失败
    let has_space = path_str.contains(' ');
    // 父目录可写：PyInstaller 解压 _internal/、写日志、写配置都需要这个
    let parent = exe_path.parent();
    let parent_writable = parent
        .and_then(|p| {
            let probe = p.join(".fastread_write_probe");
            match std::fs::write(&probe, b"x") {
                Ok(_) => {
                    let _ = std::fs::remove_file(&probe);
                    Some(true)
                }
                Err(_) => Some(false),
            }
        })
        .unwrap_or(false);

    InstallPathDiagnostics {
        exe_path: path_str,
        path_has_non_ascii: has_non_ascii,
        path_has_space: has_space,
        parent_writable,
        platform: std::env::consts::OS.to_string(),
    }
}

// Tauri 命令：让前端按需重新查询诊断结果（比如用户卸载到新目录后重启）
#[tauri::command]
fn get_install_path_diagnostics() -> InstallPathDiagnostics {
    let exe_path = env::current_exe().unwrap_or_default();
    analyze_install_path(&exe_path)
}
