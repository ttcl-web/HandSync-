/**
 * 双舵机 PWM 驱动模块 (TIM2 硬件PWM)
 *
 * 硬件: STM32F103C8T6
 *   舵机1 (PAN  转向底座): PA0 = TIM2_CH1
 *   舵机2 (TILT 俯仰关节): PA1 = TIM2_CH2
 *
 * PWM参数: 50Hz (20ms周期), 500~2500us 对应 0°~180°
 */

#ifndef __STEER_H
#define __STEER_H

#include "stm32f10x.h"

/* ========== 引脚宏定义 ========== */
#define STEER_PAN_PORT    GPIOA
#define STEER_PAN_PIN     GPIO_Pin_0          // PA0 - TIM2_CH1

#define STEER_TILT_PORT   GPIOA
#define STEER_TILT_PIN    GPIO_Pin_1          // PA1 - TIM2_CH2

/* ========== 角度范围 ========== */
#define SERVO_ANGLE_MIN   0
#define SERVO_ANGLE_MAX   180
#define SERVO_ANGLE_MID   90                   // 中点

/* ========== PWM参数 ========== */
#define SERVO_PWM_MIN     500                  // 0°  脉宽 (us)
#define SERVO_PWM_MAX     2500                 // 180° 脉宽 (us)
#define SERVO_PWM_PERIOD  20000                // 20ms 周期 (us)

/* ========== 函数声明 ========== */
void Steer_Init(void);                          // 初始化双舵机PWM
void Steer_SetPan(uint16_t angle);              // 设置PAN角度 (0~180)
void Steer_SetTilt(uint16_t angle);             // 设置TILT角度 (0~180)
void Steer_SetBoth(uint16_t pan, uint16_t tilt); // 同时设置两个角度
uint16_t Steer_GetPan(void);                    // 读取当前PAN角度
uint16_t Steer_GetTilt(void);                   // 读取当前TILT角度

#endif
