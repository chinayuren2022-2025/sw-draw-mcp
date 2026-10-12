# KVM/QEMU 离线安装方法（Ubuntu 服务器无法联网）

## 1. 原理

在一台**与目标服务器 Ubuntu 版本相同的联网电脑**上，用 `apt` 下载 KVM/QEMU 及全部依赖的 `.deb` 包，然后拷贝到离线服务器，用 `dpkg` 或 `apt` 从本地 `.deb` 安装。

## 1.5 如果你只有 Windows 电脑：用 WSL2 准备 .deb

如果你没有联网的 Linux 电脑，可以在 Windows 电脑上使用 **WSL2（Ubuntu）** 完成下载：

1. Windows 上安装/启用 WSL2：
   ```powershell
   wsl --install -d Ubuntu
   ```
2. 进入 WSL2 Ubuntu（WSL2 默认能联网）：
   ```bash
   sudo apt update
   sudo apt install --download-only      qemu-system-x86 qemu-utils libvirt-daemon-system      libvirt-clients virtinst virt-manager
   ```
3. 把下载好的 `.deb` 从 WSL2 导出到 Windows 目录：
   ```bash
   mkdir -p /mnt/d/kvm-debs
   sudo cp /var/cache/apt/archives/*.deb /mnt/d/kvm-debs/
   ```
4. 在 Windows 上通过 U 盘/WinSCP/SCP，把 `D:\kvm-debs` 传到离线 Ubuntu 服务器：
   ```text
   /data/kvm-debs/
   ```
5. 在离线服务器上安装：
   ```bash
   cd /data/kvm-debs
   sudo apt install ./*.deb
   ```

> 前提：WSL2 中的 Ubuntu 版本建议与目标服务器版本一致，避免依赖版本差异。
> 如果版本不一致，可在 WSL2 中安装相同版本容器，或手动核对依赖。

## 2. 在联网电脑上准备

### 2.1 确认系统版本与架构

```bash
lsb_release -a
uname -m
```

目标服务器和联网电脑建议：

- 相同 Ubuntu 版本
- 相同架构（通常都是 x86_64）

### 2.2 下载 KVM/QEMU 相关包

```bash
sudo apt update
sudo apt install --download-only \
  qemu-system-x86 \
  qemu-utils \
  libvirt-daemon-system \
  libvirt-clients \
  virtinst \
  virt-manager
```

`--download-only` 会把这些包以及依赖全部下载到：

```text
/var/cache/apt/archives/*.deb
```

### 2.3 拷贝到 U 盘/移动硬盘

```bash
mkdir -p /media/usb/kvm-debs
sudo cp /var/cache/apt/archives/*.deb /media/usb/kvm-debs/
```

也可以直接通过局域网 SCP 传到离线服务器：

```bash
scp /var/cache/apt/archives/*.deb user@server_ip:/data/kvm-debs/
```

## 3. 在离线服务器上安装

### 3.1 把 .deb 放到一个目录

假设放在：

```text
/data/kvm-debs/
```

### 3.2 安装

```bash
cd /data/kvm-debs
sudo apt install ./*.deb
```

如果 `apt install ./*.deb` 不可用，使用：

```bash
sudo dpkg -i *.deb
```

若 `dpkg` 提示依赖未满足，再执行：

```bash
sudo apt-get install -f
```

但离线服务器不能联网时，`install -f` 可能失败；所以必须确保前面 `--download-only` 已经把依赖全部下载完整。

## 4. 启动与配置

```bash
# 启动 libvirtd
sudo systemctl enable --now libvirtd

# 把当前用户加入 kvm 和 libvirt 组
sudo usermod -aG kvm,libvirt $USER

# 重新登录后验证
virsh version
virt-install --version
```

## 5. 检查 CPU 虚拟化支持

```bash
egrep -c '(vmx|svm)' /proc/cpuinfo
```

如果返回 `0`，说明 CPU 未开启硬件虚拟化，需要在 BIOS 中开启 VT-x/AMD-V，否则 KVM 性能会很差或无法使用。

## 6. 创建 Windows 虚拟机（离线）

把 Windows ISO 和 virtio 驱动（如果 Windows 安装时需要 virtio 磁盘/网卡驱动）放到服务器：

```bash
sudo virt-install \
  --name win11 \
  --ram 8192 \
  --vcpus 4 \
  --disk path=/var/lib/libvirt/images/win11.qcow2,size=80,format=qcow2 \
  --cdrom /data/iso/Win11.iso \
  --os-variant windows11 \
  --network network=default \
  --graphics spice \
  --noautoconsole
```

> 如果使用 Windows 10，可把 `--os-variant` 改成 `win10`。
> 如果没有 virtio 驱动，Windows 可能找不到磁盘/网卡；建议在联网电脑提前下载 virtio-win 镜像，一并传入服务器。

## 7. 离线安装检查清单

- [ ] 联网电脑与服务器 Ubuntu 版本一致
- [ ] `qemu-system-x86`、`libvirt-daemon-system`、`virtinst`、`virt-manager` 等包已下载
- [ ] `.deb` 已传输到服务器
- [ ] `sudo apt install ./*.deb` 成功
- [ ] `virsh version` 正常
- [ ] CPU 虚拟化已开启
- [ ] Windows ISO 已传到服务器
