import { createRouter, createWebHistory } from 'vue-router'

import Dashboard from './pages/op/Dashboard.vue'
import Schedule from './pages/op/Schedule.vue'
import Phone from './pages/op/Phone.vue'
import OrderDetail from './pages/op/OrderDetail.vue'
import CastToday from './pages/cast/CastToday.vue'
import CuMypage from './pages/cu/CuMypage.vue'
import CuBooking from './pages/cu/CuBooking.vue'
import CuSubmitted from './pages/cu/CuSubmitted.vue'

const routes = [
  { path: '/', redirect: '/op/dashboard' },
  { path: '/op/dashboard', name: 'dashboard', component: Dashboard },
  { path: '/op/schedule', name: 'schedule', component: Schedule },
  { path: '/op/phone', name: 'phone', component: Phone },
  { path: '/op/orders/:id', name: 'order-detail', component: OrderDetail, props: true },

  // Cast
  { path: '/cast/today', name: 'cast-today', component: CastToday },

  // Customer
  { path: '/cu/mypage', name: 'cu-mypage', component: CuMypage },
  { path: '/cu/booking', name: 'cu-booking', component: CuBooking },
  { path: '/cu/submitted', name: 'cu-submitted', component: CuSubmitted },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
