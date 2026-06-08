/**
 * 双舵机 PWM 驱动实现 (TIM2_CH1 + TIM2_CH2)
 *
 * 硬件: STM32F103C8T6
 *   PA0 = TIM2_CH1 = PAN  转向底座  0°~180°
 *   PA1 = TIM2_CH2 = TILT 俯仰关节  0°~180°
 *
 * PWM: 50Hz (20ms周期), 500~2500us 对应 0°~180°
 */

#include "steer.h"

/* ========== 当前角度 ========== */
static uint16_t pan_angle  = SERVO_ANGLE_MID;
static uint16_t tilt_angle = SERVO_ANGLE_MID;

/* ========== 角度→脉宽 (us) ========== */
static uint16_t angle_to_pulse(uint16_t angle)
{
    if (angle > SERVO_ANGLE_MAX) angle = SERVO_ANGLE_MAX;
    return SERVO_PWM_MIN + (uint32_t)angle * (SERVO_PWM_MAX - SERVO_PWM_MIN) / SERVO_ANGLE_MAX;
}

/* ========== 初始化 ========== */
void Steer_Init(void)
{
    GPIO_InitTypeDef       GPIO_InitStructure;
    TIM_TimeBaseInitTypeDef TIM_TimeBaseStructure;
    TIM_OCInitTypeDef       TIM_OCInitStructure;

    /* --- 时钟使能 --- */
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2,  ENABLE);

    /* --- PA0 + PA1 复用推挽输出 --- */
    GPIO_InitStructure.GPIO_Pin   = GPIO_Pin_0 | GPIO_Pin_1;          // PA0(TIM2_CH1) | PA1(TIM2_CH2)
    GPIO_InitStructure.GPIO_Mode  = GPIO_Mode_AF_PP;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStructure);

    /* --- TIM2 时基: 72MHz / 72 = 1MHz → 20ms周期 --- */
    TIM_TimeBaseStructure.TIM_Prescaler         = 72 - 1;
    TIM_TimeBaseStructure.TIM_CounterMode       = TIM_CounterMode_Up;
    TIM_TimeBaseStructure.TIM_Period            = SERVO_PWM_PERIOD - 1;
    TIM_TimeBaseStructure.TIM_ClockDivision     = TIM_CKD_DIV1;
    TIM_TimeBaseStructure.TIM_RepetitionCounter = 0;
    TIM_TimeBaseInit(TIM2, &TIM_TimeBaseStructure);

    /* --- CH1 (PA0) PAN --- */
    TIM_OCInitStructure.TIM_OCMode      = TIM_OCMode_PWM1;
    TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Enable;
    TIM_OCInitStructure.TIM_OCPolarity  = TIM_OCPolarity_High;
    TIM_OCInitStructure.TIM_Pulse       = angle_to_pulse(SERVO_ANGLE_MID);
    TIM_OC1Init(TIM2, &TIM_OCInitStructure);
    TIM_OC1PreloadConfig(TIM2, TIM_OCPreload_Enable);

    /* --- CH2 (PA1) TILT --- */
    TIM_OCInitStructure.TIM_Pulse = angle_to_pulse(SERVO_ANGLE_MID);
    TIM_OC2Init(TIM2, &TIM_OCInitStructure);
    TIM_OC2PreloadConfig(TIM2, TIM_OCPreload_Enable);

    /* --- 启动 --- */
    TIM_ARRPreloadConfig(TIM2, ENABLE);
    TIM_Cmd(TIM2, ENABLE);

    /* 初始归中 */
    GPIO_ResetBits(STEER_PAN_PORT,  STEER_PAN_PIN);
    GPIO_ResetBits(STEER_TILT_PORT, STEER_TILT_PIN);
}

/* ========== 设置 PAN 角度 ========== */
void Steer_SetPan(uint16_t angle)
{
    if (angle > SERVO_ANGLE_MAX) angle = SERVO_ANGLE_MAX;
    TIM_SetCompare1(TIM2, angle_to_pulse(angle));
    pan_angle = angle;
}

/* ========== 设置 TILT 角度 ========== */
void Steer_SetTilt(uint16_t angle)
{
    if (angle > SERVO_ANGLE_MAX) angle = SERVO_ANGLE_MAX;
    TIM_SetCompare2(TIM2, angle_to_pulse(angle));
    tilt_angle = angle;
}

/* ========== 同时设置两个角度 ========== */
void Steer_SetBoth(uint16_t pan, uint16_t tilt)
{
    if (pan  > SERVO_ANGLE_MAX) pan  = SERVO_ANGLE_MAX;
    if (tilt > SERVO_ANGLE_MAX) tilt = SERVO_ANGLE_MAX;

    TIM_SetCompare1(TIM2, angle_to_pulse(pan));
    TIM_SetCompare2(TIM2, angle_to_pulse(tilt));

    pan_angle  = pan;
    tilt_angle = tilt;
}

/* ========== 读取当前角度 ========== */
uint16_t Steer_GetPan(void)
{
    return pan_angle;
}

uint16_t Steer_GetTilt(void)
{
    return tilt_angle;
}
