package cn.zipingshushu.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private WebView web;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private PyObject runtime;
    private byte[] pendingExport;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(0xff121215);
        getWindow().setNavigationBarColor(0xff0b0c0e);
        web = new WebView(this);
        web.setBackgroundColor(0xff0b0c0e);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(false);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(false);
        web.getSettings().setSaveFormData(false);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                // Only the bundled document has the Python bridge. Never load remote pages into it.
                return true;
            }
        });
        web.addJavascriptInterface(new Bridge(), "ZipingNative");
        setContentView(web);
        executor.execute(() -> {
            try {
                File data = new File(getFilesDir(), "core-data-v1");
                copyAssets("core-data", data);
                if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
                runtime = Python.getInstance().getModule("mobile_runtime");
                runtime.callAttr("initialize", data.getAbsolutePath(), getFilesDir().getAbsolutePath());
                try (InputStream input = getAssets().open("index.html")) {
                    String page = new String(readBytes(input), StandardCharsets.UTF_8);
                    runOnUiThread(() -> web.loadDataWithBaseURL("https://ziping.local/", page, "text/html", "UTF-8", null));
                }
            } catch (Exception ignored) {
                runOnUiThread(() -> new AlertDialog.Builder(this).setTitle("子平术数")
                    .setMessage("本地资源初始化未完成，请重新打开应用。").setPositiveButton("关闭", (d,w)->finish()).show());
            }
        });
    }

    private static byte[] readBytes(InputStream input) throws java.io.IOException {
        java.io.ByteArrayOutputStream output = new java.io.ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int n;
        while ((n = input.read(buffer)) != -1) output.write(buffer, 0, n);
        return output.toByteArray();
    }

    private void copyAssets(String path, File destination) throws java.io.IOException {
        String[] children = getAssets().list(path);
        if (children != null && children.length > 0) {
            if (!destination.exists() && !destination.mkdirs()) throw new java.io.IOException();
            for (String name : children) copyAssets(path + "/" + name, new File(destination, name));
        } else if (!destination.exists()) {
            File parent = destination.getParentFile();
            if (parent != null) parent.mkdirs();
            try (InputStream input = getAssets().open(path); OutputStream out = new FileOutputStream(destination)) {
                byte[] buffer = new byte[8192];
                int n;
                while ((n=input.read(buffer))!=-1) out.write(buffer,0,n);
            }
        }
    }

    private class Bridge {
        @JavascriptInterface public void call(String id, String method, String payload) {
            if (!id.matches("[0-9]{1,12}") || payload.length() > 50000) return;
            executor.execute(() -> {
                String output;
                try { output = runtime.callAttr("dispatch", method, payload).toString(); }
                catch (Exception ignored) { output = "{\"ok\":false,\"error\":\"本地操作未完成，请重新打开应用。\"}"; }
                String script = "window.receiveNative(" + JSONObject.quote(id) + "," + JSONObject.quote(output) + ")";
                runOnUiThread(() -> web.evaluateJavascript(script, null));
            });
        }

        @JavascriptInterface public void copyWechat() {
            runOnUiThread(() -> {
                ClipboardManager manager = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                manager.setPrimaryClip(ClipData.newPlainText("作者微信", "bxzgf-bxbgf"));
            });
        }

        @JavascriptInterface public void save(String filename, String encoded, String mime) {
            if (encoded.length() > 8000000 || !filename.matches("子平术数-解读报告\\.(html|txt|json)")) return;
            byte[] bytes;
            try { bytes = android.util.Base64.decode(encoded, android.util.Base64.DEFAULT); }
            catch (Exception ignored) { return; }
            runOnUiThread(() -> {
                if (pendingExport != null) return;
                pendingExport = bytes;
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType(mime);
                intent.putExtra(Intent.EXTRA_TITLE, filename);
                try { startActivityForResult(intent, 201); }
                catch (Exception ignored) { pendingExport = null; }
            });
        }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == 201) {
            byte[] bytes = pendingExport;
            pendingExport = null;
            if (result == RESULT_OK && data != null && data.getData() != null && bytes != null) {
                try (OutputStream output = getContentResolver().openOutputStream(data.getData())) {
                    if (output != null) output.write(bytes);
                } catch (Exception ignored) {
                    new AlertDialog.Builder(this).setMessage("文件未能保存，请重新选择保存位置。").setPositiveButton("知道了",null).show();
                }
            }
        }
    }

    @Override public void onBackPressed() {
        new AlertDialog.Builder(this).setMessage("退出子平术数？未下载的报告和本次模型密钥不会保留。")
            .setNegativeButton("继续使用",null).setPositiveButton("退出",(d,w)->finish()).show();
    }
    @Override protected void onDestroy() {
        executor.shutdown();
        if (web != null) { web.removeJavascriptInterface("ZipingNative"); web.destroy(); }
        super.onDestroy();
    }
}
