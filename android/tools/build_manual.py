"""Build the small Android shell without Gradle, from official Android SDK tools.

Usage: python3 android/tools/build_manual.py --sdk /path/to/sdk-extract --out /path/fixed.apk
SDK directory contains android-35/android.jar and android-15/{aapt2,lib/d8.jar,...}
from platform-35_r02.zip and build-tools_r35_linux.zip. Development signing only.
"""
from pathlib import Path
import argparse,os,subprocess,zipfile,xml.etree.ElementTree as ET

p=argparse.ArgumentParser();p.add_argument('--sdk',required=True);p.add_argument('--out',required=True);args=p.parse_args()
root=Path(__file__).resolve().parents[1];sdk=Path(args.sdk).resolve();output=Path(args.out).resolve()
work=root/'build'/'manual';work.mkdir(parents=True,exist_ok=True)
tools=sdk/'android-15';jar=sdk/'android-35'/'android.jar'
for binary in ('aapt2','zipalign','dexdump'):(tools/binary).chmod(0o755)
def run(*command):
 print('+',*map(str,command),flush=True);subprocess.run(list(map(str,command)),check=True)
# The app remains a local development client with HTTP allowed and same-origin picker.
ns='http://schemas.android.com/apk/res/android';ET.register_namespace('android',ns)
tree=ET.parse(root/'app/src/main/AndroidManifest.xml');manifest=tree.getroot()
manifest.set('package','fr.meetpoint.app.debug');manifest.set('{'+ns+'}versionCode','5');manifest.set('{'+ns+'}versionName','0.4.2')
uses=ET.Element('uses-sdk',{'{'+ns+'}minSdkVersion':'26','{'+ns+'}targetSdkVersion':'35'});manifest.insert(0,uses)
app=manifest.find('application');app.set('{'+ns+'}usesCleartextTraffic','true');app.set('{'+ns+'}debuggable','true')
app.find('activity').set('{'+ns+'}name','fr.pointcommun.app.MainActivity')
mp=work/'AndroidManifest.xml';tree.write(mp,encoding='utf-8',xml_declaration=True)
resources=work/'resources.zip';run(tools/'aapt2','compile','--dir',root/'app/src/main/res','-o',resources)
unsigned=work/'resources.apk';run(tools/'aapt2','link','-I',jar,'--manifest',mp,'-o',unsigned,resources)
classes=work/'classes';classes.mkdir(exist_ok=True)
config=work/'BuildConfig.java';config.write_text('package fr.pointcommun.app; public final class BuildConfig { public static final boolean DEBUG=true; }\n')
sources=list((root/'app/src/main/java').rglob('*.java'))+[config]
run('java','com.sun.tools.javac.Main','-source','8','-target','8','-bootclasspath',jar,'-d',classes,*sources)
jarclasses=work/'classes.jar'
with zipfile.ZipFile(jarclasses,'w') as z:
 for entry in classes.rglob('*.class'):z.write(entry,entry.relative_to(classes))
dex=work/'dex';dex.mkdir(exist_ok=True)
run('java','-cp',tools/'lib/d8.jar','com.android.tools.r8.D8','--lib',jar,'--min-api','26','--output',dex,jarclasses)
with zipfile.ZipFile(unsigned,'a',zipfile.ZIP_DEFLATED) as z:
 for entry in dex.glob('*.dex'):z.write(entry,entry.name)
aligned=work/'aligned.apk';run(tools/'zipalign','-f','4',unsigned,aligned)
key=root/'debug-signing/meetpoint-debug.keystore';key.parent.mkdir(exist_ok=True)
if not key.exists():
 run('keytool','-genkeypair','-keystore',key,'-storepass','android','-keypass','android','-alias','meetpointdebug','-keyalg','RSA','-keysize','2048','-validity','10000','-dname','CN=MeetPoint Debug,O=University Project,C=FR')
output.parent.mkdir(parents=True,exist_ok=True)
run('java','-jar',tools/'lib/apksigner.jar','sign','--ks',key,'--ks-key-alias','meetpointdebug','--ks-pass','pass:android','--key-pass','pass:android','--out',output,aligned)
run('java','-jar',tools/'lib/apksigner.jar','verify','--verbose','--print-certs',output)
run(tools/'aapt2','dump','badging',output)
print('APK:',output,flush=True)
