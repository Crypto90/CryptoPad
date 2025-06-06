# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['CryptoPad.py'],
    pathex=[],
    binaries=[],
    datas=[],
	hiddenimports=[
		'engineio.async_drivers.eventlet', 
		'eventlet.hubs.epolls', 
		'eventlet.hubs.kqueue', 
		'eventlet.hubs.selects', 
		'dns', 
		'dns.asyncbackend', 
		'dns.asyncquery', 
		'dns.asyncresolver', 
		'dns.e164', 
		'dns.namedict', 
		'dns.tsigkeyring', 
		'dns.versioned',
		'dns.dnssec',
		'dns.hash',
		'dns.tsigkeyring',
		'dns.update',
		'dns.version',
		'dns.zone'
	],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CryptoPad',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
