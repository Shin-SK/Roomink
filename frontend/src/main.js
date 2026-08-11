import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'
import { initializeMonitoring } from './monitoring.js'

import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap/dist/js/bootstrap.bundle.min.js'
import '@tabler/icons-webfont/dist/tabler-icons.min.css'
import './assets/css/styles.scss'

const app = createApp(App)
initializeMonitoring(app)
app.use(router).mount('#app')
