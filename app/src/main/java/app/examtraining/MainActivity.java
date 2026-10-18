package app.examtraining;

import android.app.Activity;
import android.content.pm.PackageInfo;
import android.content.res.Configuration;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.window.OnBackInvokedDispatcher;
import android.widget.ScrollView;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private static final String TAG = "ExamTraining";
    private static final String START_URL = "file:///android_asset/index.html";

    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        try {
            createAndLoadWebView();
        } catch (Throwable error) {
            Log.e(TAG, "Application startup failed", error);
            showStartupError(error);
        }
    }

    private void createAndLoadWebView() {
        WebView view = new WebView(this);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            view.setWebViewClient(new RendererAwareWebViewClient());
        } else {
            view.setWebViewClient(new LocalOnlyWebViewClient());
        }

        WebSettings settings = view.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(false);
        settings.setBlockNetworkLoads(true);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);

        // The web UI asks Android directly for the system theme instead of
        // relying only on WebView's prefers-color-scheme implementation.
        view.addJavascriptInterface(new NativeThemeBridge(), "NativeTheme");

        webView = view;
        setContentView(view);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                    this::handleBackNavigation
            );
        }

        view.loadUrl(START_URL);
    }

    private void handleBackNavigation() {
        WebView view = webView;
        if (view == null) {
            finish();
            return;
        }

        view.evaluateJavascript(
                "(function(){try{return !!(window.examTrainingHandleBack && window.examTrainingHandleBack());}catch(e){return false;}})()",
                result -> {
                    if (!"true".equals(result)) {
                        finish();
                    }
                }
        );
    }

    @Override
    public void onBackPressed() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            // Android 13+ is handled through OnBackInvokedDispatcher above.
            handleBackNavigation();
            return;
        }
        handleBackNavigation();
    }

    private boolean isSystemDarkTheme() {
        int nightMode = getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        return nightMode == Configuration.UI_MODE_NIGHT_YES;
    }

    private void applySystemBarStyle(String colorHex, boolean darkIcons) {
        final int color;
        try {
            color = Color.parseColor(colorHex);
        } catch (IllegalArgumentException error) {
            Log.w(TAG, "Invalid system bar color from web UI: " + colorHex, error);
            return;
        }

        runOnUiThread(() -> {
            Window window = getWindow();
            window.setStatusBarColor(color);
            window.setNavigationBarColor(color);

            View decor = window.getDecorView();
            int flags = decor.getSystemUiVisibility();
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                if (darkIcons) {
                    flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
                } else {
                    flags &= ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
                }
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                if (darkIcons) {
                    flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
                } else {
                    flags &= ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
                }
            }
            decor.setSystemUiVisibility(flags);
        });
    }

    private final class NativeThemeBridge {
        @JavascriptInterface
        public boolean isSystemDark() {
            return isSystemDarkTheme();
        }

        @JavascriptInterface
        public void setSystemBars(String colorHex, boolean darkIcons) {
            applySystemBarStyle(colorHex, darkIcons);
        }
    }

    private void showStartupError(Throwable error) {
        StringBuilder text = new StringBuilder();
        text.append("ExamTraining не удалось запустить.\n\n");
        text.append("Android: ").append(Build.VERSION.RELEASE)
                .append(" (API ").append(Build.VERSION.SDK_INT).append(")\n");

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            try {
                PackageInfo webViewPackage = WebView.getCurrentWebViewPackage();
                if (webViewPackage != null) {
                    text.append("WebView: ").append(webViewPackage.packageName)
                            .append(" ").append(webViewPackage.versionName).append("\n");
                } else {
                    text.append("WebView: не найден\n");
                }
            } catch (Throwable ignored) {
                text.append("WebView: не удалось определить версию\n");
            }
        }

        text.append("\nОшибка: ").append(error.getClass().getName());
        if (error.getMessage() != null && !error.getMessage().trim().isEmpty()) {
            text.append("\n").append(error.getMessage());
        }
        text.append("\n\nЕсли ошибка связана с WebView, обновите Android System WebView или Chrome и перезапустите приложение.");
        text.append("\n\nСделайте скриншот этого экрана: по нему можно определить точную причину.");

        boolean dark = isSystemDarkTheme();
        int background = dark ? Color.rgb(17, 19, 24) : Color.rgb(243, 244, 246);
        int foreground = dark ? Color.rgb(243, 244, 246) : Color.rgb(17, 19, 24);

        TextView message = new TextView(this);
        int padding = Math.round(20 * getResources().getDisplayMetrics().density);
        message.setPadding(padding, padding, padding, padding);
        message.setText(text.toString());
        message.setTextColor(foreground);
        message.setTextSize(16f);
        message.setTextIsSelectable(true);

        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(background);
        scroll.addView(message, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));
        setContentView(scroll);
        applySystemBarStyle(dark ? "#111318" : "#F3F4F6", !dark);
    }

    private static boolean isAllowedLocalUrl(String url) {
        return url != null && (url.startsWith("file:///android_asset/") || "about:blank".equals(url));
    }

    private static class LocalOnlyWebViewClient extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, String url) {
            return !isAllowedLocalUrl(url);
        }
    }

    private final class RendererAwareWebViewClient extends LocalOnlyWebViewClient {
        @Override
        public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
            boolean didCrash = detail != null && detail.didCrash();
            Log.e(TAG, didCrash
                    ? "WebView renderer process crashed"
                    : "WebView renderer process was killed by the system");

            if (view == webView) {
                webView = null;
            }
            try {
                if (view.getParent() instanceof ViewGroup) {
                    ((ViewGroup) view.getParent()).removeView(view);
                }
                view.destroy();
            } catch (Throwable cleanupError) {
                Log.w(TAG, "Failed to clean up terminated WebView", cleanupError);
            }

            showStartupError(new RuntimeException(didCrash
                    ? "Процесс отображения Android WebView аварийно завершился."
                    : "Android завершил процесс WebView, вероятно из-за нехватки памяти."));
            return true;
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            try {
                webView.stopLoading();
                webView.loadUrl("about:blank");
                webView.clearHistory();
                webView.removeAllViews();
                webView.destroy();
            } catch (Throwable error) {
                Log.w(TAG, "WebView cleanup failed", error);
            } finally {
                webView = null;
            }
        }
        super.onDestroy();
    }
}
