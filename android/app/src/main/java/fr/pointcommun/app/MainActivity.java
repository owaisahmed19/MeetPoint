package fr.pointcommun.app;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.GeolocationPermissions;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;
import android.widget.Toast;

/** Installable foreground client for the shared PointCommun web application. */
public final class MainActivity extends Activity {
    private static final int LOCATION_REQUEST = 42;
    private static final int PHOTO_REQUEST = 43;
    private static final String DEFAULT_SERVER = "https://revolution-arbor-card-atlanta.trycloudflare.com";
    private WebView web;
    private String trustedOrigin = "";
    private String pendingOrigin;
    private GeolocationPermissions.Callback pendingCallback;
    private ValueCallback<Uri[]> pendingPhoto;
    private String photoOrigin;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(243,246,248));
        root.setPadding(0, getStatusBarHeight(), 0, 0);
        web = new WebView(this);
        root.addView(web,new LinearLayout.LayoutParams(-1,0,1));
        setContentView(root);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setGeolocationEnabled(true);
        // The page still controls consent/mute; allow its later invitation chime.
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setAllowFileAccess(false);
        // Permit only user-selected document-provider content. File access stays off.
        settings.setAllowContentAccess(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request) {
                Uri uri=request.getUrl();
                if (origin(uri).equals(trustedOrigin)) return false;
                if ("https".equals(uri.getScheme()) || "http".equals(uri.getScheme())) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW,uri)); }
                    catch (Exception ex) { notice("No browser is available."); }
                }
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                cancelPhoto();
                String current = origin(Uri.parse(view.getUrl() == null ? "" : view.getUrl()));
                if (trustedOrigin.isEmpty() || !current.equals(trustedOrigin)) {
                    callback.onReceiveValue(null);
                    return true;
                }
                pendingPhoto = callback;
                photoOrigin = trustedOrigin;
                Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE);
                pick.setType("image/*");
                pick.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"image/png", "image/jpeg", "image/webp"});
                pick.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                try { startActivityForResult(pick, PHOTO_REQUEST); }
                catch (Exception ex) { cancelPhoto(); notice("No image picker is available."); }
                return true;
            }
            @Override public void onGeolocationPermissionsShowPrompt(String requested,GeolocationPermissions.Callback callback) {
                if (!origin(Uri.parse(requested)).equals(trustedOrigin)) { callback.invoke(requested,false,false); return; }
                if (hasLocation()) { callback.invoke(requested,true,false); return; }
                cancelPending();
                pendingOrigin=requested;
                pendingCallback=callback;
                requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION},LOCATION_REQUEST);
            }
        });
        openServer();
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private int getStatusBarHeight() {
        int id=getResources().getIdentifier("status_bar_height","dimen","android");
        return id>0 ? getResources().getDimensionPixelSize(id) : 0;
    }
    private static String origin(Uri uri) {
        if (uri==null || uri.getScheme()==null || uri.getHost()==null) return "";
        String scheme=uri.getScheme().toLowerCase(java.util.Locale.ROOT);
        int port=uri.getPort();
        if (("https".equals(scheme)&&port==443)||("http".equals(scheme)&&port==80)) port=-1;
        return scheme+"://"+uri.getHost().toLowerCase(java.util.Locale.ROOT)+(port==-1?"":":"+port);
    }
    private void openServer() {
        Uri uri=Uri.parse(DEFAULT_SERVER);
        String scheme=uri.getScheme();
        if (uri.getHost()==null || uri.getUserInfo()!=null || !"https".equals(scheme)) return;
        pauseSharing();
        cancelPending();
        cancelPhoto();
        GeolocationPermissions.getInstance().clearAll();
        trustedOrigin=origin(uri);
        web.loadUrl(trustedOrigin+"/");
    }
    private boolean hasLocation() {
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION)==PackageManager.PERMISSION_GRANTED;
    }
    private void cancelPending() {
        if (pendingCallback!=null) pendingCallback.invoke(pendingOrigin,false,false);
        pendingCallback=null;
        pendingOrigin=null;
    }
    private void cancelPhoto() {
        if (pendingPhoto != null) pendingPhoto.onReceiveValue(null);
        pendingPhoto = null;
        photoOrigin = null;
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != PHOTO_REQUEST || pendingPhoto == null) return;
        Uri selected = data == null ? null : data.getData();
        Uri[] accepted = null;
        String current = origin(Uri.parse(web.getUrl() == null ? "" : web.getUrl()));
        if (result == RESULT_OK && selected != null && "content".equals(selected.getScheme())
                && trustedOrigin.equals(photoOrigin) && trustedOrigin.equals(current)) {
            try {
                String type = getContentResolver().getType(selected);
                if ("image/png".equals(type) || "image/jpeg".equals(type) || "image/webp".equals(type))
                    accepted = new Uri[]{selected};
            } catch (SecurityException ignored) { }
        }
        ValueCallback<Uri[]> callback = pendingPhoto;
        pendingPhoto = null;
        photoOrigin = null;
        callback.onReceiveValue(accepted);
        if (result == RESULT_OK && accepted == null) notice("Choose a PNG, JPEG or WebP image.");
    }
    @Override public void onRequestPermissionsResult(int code,String[] permissions,int[] results) {
        super.onRequestPermissionsResult(code,permissions,results);
        if(code==LOCATION_REQUEST&&pendingCallback!=null) {
            pendingCallback.invoke(pendingOrigin,hasLocation()&&origin(Uri.parse(pendingOrigin)).equals(trustedOrigin),false);
            pendingCallback=null;
            pendingOrigin=null;
        }
    }
    private void pauseSharing() {
        if(web!=null) web.evaluateJavascript("window.dispatchEvent(new Event('pointcommun:pause'));",null);
    }
    @Override protected void onPause() { pauseSharing(); cancelPending(); if(web!=null)web.onPause(); super.onPause(); }
    @Override protected void onResume() { super.onResume(); if(web!=null)web.onResume(); }
    @Override protected void onDestroy() { cancelPending(); cancelPhoto(); if(web!=null){web.stopLoading();web.destroy();} super.onDestroy(); }
    @Override public void onBackPressed() { if(web!=null&&web.canGoBack())web.goBack(); else super.onBackPressed(); }
    private void notice(String text) { Toast.makeText(this,text,Toast.LENGTH_LONG).show(); }
}
