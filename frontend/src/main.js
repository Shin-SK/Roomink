import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'
import { initializeMonitoring } from './monitoring.js'
import { preparePasswordResetLink } from './passwordResetLink.js'

import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap/dist/js/bootstrap.bundle.min.js'
import './assets/icons.css'
import './assets/css/styles.scss'

const app = createApp(App)
// Remove recovery secrets before monitoring or router navigation can observe them.
preparePasswordResetLink(window.location, window.history)
initializeMonitoring(app)
app.use(router).mount('#app')
