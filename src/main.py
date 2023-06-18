import dataclasses
import functools
import itertools
import math
import os
import sys
import time

import pygame

import levels


WINDOW_RES = 1280, 720
PIXEL_SIZE = 4
SIZE = WIDTH, HEIGHT = WINDOW_RES[0] // PIXEL_SIZE, WINDOW_RES[1] // PIXEL_SIZE
TILE_SIZE = 16
FPS = 60


def main():
    pygame.init()
    screen = pygame.display.set_mode(WINDOW_RES)
    clock = pygame.time.Clock()

    camera = Camera()
    surface = CameraSurface(camera, SIZE)

    current_level = 0
    previous_level = 1
    level_completions = {}
    for i in range(levels.MIN_LEVEL_NUMBER, levels.MAX_LEVEL_NUMBER + 1):
        level_completions[i] = LevelCompletion(i, False)

    world = create_world(
        current_level, previous_level, level_completions, camera
    )

    font_renderer = FontRenderer()
    font_renderer_2 = FontRenderer2()

    while True:
        if not world.player.alive:
            if world.player.entered_door is not None:
                previous_level = current_level
                current_level = world.player.entered_door.destination_level
                if not world.player.entered_door.start:
                    level_completions[previous_level].completed = True
            world = create_world(
                current_level, previous_level, level_completions, camera
            )

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sys.exit()

        t0 = time.time()

        world.level.snakes.update()
        world.level.moving_platforms.update()
        world.player.update()
        world.player.slashes.update()
        if not world.player.is_dying():
            camera.follow(world.player)
        world.water_tiles.update()

        print(f'update: {time.time() - t0:4f} ', end='')

        t0 = time.time()

        surface.fill((93, 152, 141))

        world.water_tiles.draw(surface)
        world.level.background_tiles.draw(surface)
        for renderer in world.level.endless_background_renderers:
            renderer.draw(surface)
        world.level.tiles.draw(surface)
        world.level.moving_platforms.draw(surface)
        world.level.doors.draw(surface)
        world.level.snakes.draw(surface)
        surface.blit(world.player.image, world.player.rect)
        world.player.slashes.draw(surface)

        surface.camera_mode = False
        world.door_text_viewer.draw(surface)
        surface.camera_mode = True

        text = "LEVEL 1 The quick brown fox jumped over the lazy dog."
        font_renderer.draw(surface, (22 * TILE_SIZE, 0 * TILE_SIZE), text)
        font_renderer_2.draw(surface, (22 * TILE_SIZE, 16), text)

        t02 = time.time()
        upscaled = pygame.transform.scale(surface, WINDOW_RES)
        print(f'draw.upscale: {time.time() - t02:4f} ', end='')
        screen.blit(upscaled, (0, 0))
        pygame.display.flip()

        print(f'draw: {time.time() - t0:4f} ', end='')

        delta = clock.tick(FPS)
        print(f'FPS: {clock.get_fps():4f} delta: {delta}')


class Player(pygame.sprite.Sprite):
    def __init__(self, midbottom, level):
        super().__init__()

        animations_list = [
            Animation('idle', [load_image('king.png')], 1, cycle=True),
            Animation('walk', load_images('king_walk'), 10, cycle=True),
            Animation('jump', load_images('king_jump'), 1),
            Animation('slash', load_images('king_slash'), 10),
            Animation('door', load_images('king_door'), 10),
            Animation('die', [load_image('king_dead.png')], 1, cycle=True),
        ]
        self._animations = {anim.name: anim for anim in animations_list}
        self._animation = self._animations['idle']

        self.image = self._animation.next()
        self._flip = False

        rect = pygame.Rect(0, 0, 15, 22)
        rect.midbottom = midbottom
        self._physical_body = PhysicalBody(
            rect, level.get_hittable_objects(), level.moving_platforms
        )

        self.hitbox = pygame.Rect(0, 0, 0, 0)
        self._update_hitbox()

        self.rect = self.image.get_rect()
        self._update_rect()

        self.alive = True
        self.entered_door = None
        self.slashes = pygame.sprite.Group()

        self._level = level

    def update(self):
        pressed_keys = pygame.key.get_pressed()
        pressed_buttons = pygame.mouse.get_pressed()

        action = None
        if self._animation.name in ('slash', 'door', 'die'):
            action = self._animation.name

        if action in ('slash', 'door') and self._animation.is_at_end():
            if action == 'door':
                self.alive = False
                return
            action = None

        crushed = False
        if action not in ('door', 'die'):
            crushed = (
                self._physical_body.adjust_position_after_platforms_moved()
            )
            self._update_hitbox()

        jump_speed = 0

        if (
            action not in ('die', 'door')
            and (pressed_keys[pygame.K_q] or crushed)
        ):
            action = 'die'
            jump_speed = 3

        door_to_walk_in = self.choose_door_to_walk_in()
        if (
            not action and self._physical_body.on_ground()
            and pressed_keys[pygame.K_e] and door_to_walk_in
        ):
            action = 'door'
            self._door(door_to_walk_in)

        if (
            not action and self._physical_body.on_ground()
            and pressed_buttons[0]
        ):
            action = 'slash'
            self._slash()

        if (
            not action and self._physical_body.on_ground()
            and pressed_keys[pygame.K_w]
        ):
            jump_speed = 6

        walk_movement_x = 0
        if not action:
            speed = 3
            if pressed_keys[pygame.K_a]:
                walk_movement_x -= speed
            if pressed_keys[pygame.K_d]:
                walk_movement_x += speed
        if walk_movement_x:
            self._flip = walk_movement_x < 0

        if action != 'door':
            collide = action != 'die'
            self._physical_body.update_position(
                walk_movement_x, jump_speed, collide
            )
            self._update_hitbox()

        animation = self._choose_animation(action, walk_movement_x)
        self._set_animation(animation)
        self._update_image()

        self._update_rect()

    def is_dying(self):
        return self._animation.name == 'die'

    def choose_door_to_walk_in(self):
        door_to_walk_in = None
        for door in self._level.doors:
            if door.rect.collidepoint(self.hitbox.center):
                door_to_walk_in = door
        return door_to_walk_in

    def _door(self, door_to_walk_in):
        door_to_walk_in.open()
        self.entered_door = door_to_walk_in
        self.hitbox.midbottom = door_to_walk_in.rect.midbottom

    def _slash(self):
        slash = Slash(self._animations['slash'].frame_duration, self._flip)
        if self._flip:
            slash.rect.bottomright = self.hitbox.move(10, 0).bottomleft
        else:
            slash.rect.bottomleft = self.hitbox.move(-10, 0).bottomright
        self.slashes.add(slash)

    def _choose_animation(self, action, x_walk_movement):
        animation = 'idle'
        if action:
            animation = action
        elif self._physical_body.on_ground():
            if x_walk_movement:
                animation = 'walk'
        else:
            animation = 'jump'
        return animation

    def _set_animation(self, name):
        if self._animation.name != name:
            self._animation = self._animations[name]
            self._animation.reset()
        elif self._animation.is_at_end():
            self._animation.reset()

    def _update_image(self):
        if self._animation.name not in ('jump', 'door'):
            self.image = self._animation.next()
        elif self._animation.name == 'door':
            self.image = self._animation.next()
            fraction = self._animation.next_index / len(self._animation)
            new_alpha = round(256 - fraction * 256)
            self.image.set_alpha(new_alpha)
        elif self._animation.name == 'jump':
            speed_y = self._physical_body.calculate_instantaneous_speed_y()
            if speed_y <= 0:
                self.image = self._animation[0]
            else:
                self.image = self._animation[1]

        if self._flip:
            self.image = pygame.transform.flip(self.image, True, False)

    def _update_hitbox(self):
        self.hitbox = self._physical_body.rect.copy()

    def _update_rect(self):
        offset = (-9, -10) if not self._flip else (-8, -10)
        self.rect.topleft = self.hitbox.topleft
        self.rect.move_ip(offset)


class PhysicalBody:
    def __init__(self, rect, hittable_objects, moving_platforms):
        self.rect = rect

        self._hittable_objects = hittable_objects
        self._moving_platforms = moving_platforms

        self._g = 0.33

        self._v0 = 0
        self._y0 = self.rect.y
        self._t = 0

        self._jumping = False

        self._platforms_standing_on = self._get_platforms_standing_on()

    def adjust_position_after_platforms_moved(self):
        adjustment = self._get_position_adjustment_for_platforms_standing_on()
        self.rect.move_ip(adjustment)
        if adjustment[1] != 0:
            self._reset_jump()
        crushed = self._uncollide(adjustment)
        return crushed

    def update_position(self, movement_x, jump_speed, collide):
        if jump_speed > 0:
            self._jump(jump_speed)

        self._t += 1
        y = round(self._y0 - self._v0 * self._t + self._g * self._t ** 2 / 2)

        x = self.rect.x + movement_x

        if collide:
            self._move((x, y))
        else:
            self.rect.topleft = x, y

        self._platforms_standing_on = self._get_platforms_standing_on()

    def on_ground(self):
        return bool(self._filter_sprites_standing_on(self._hittable_objects))

    def calculate_instantaneous_speed_y(self):
        return -self._v0 + self._g * self._t

    def _uncollide(self, last_move):
        old_y = self.rect.y
        crushed = uncollide_rect(self.rect, last_move, self._hittable_objects)
        if self.rect.y != old_y:
            self._reset_jump()
        return crushed

    def _get_position_adjustment_for_platforms_standing_on(self):
        if not self._platforms_standing_on:
            return 0, 0
        movements_by_y = {}
        for platform in self._platforms_standing_on:
            key = platform.last_move[1]
            value = platform.last_move[0]
            if key not in movements_by_y:
                movements_by_y[key] = 0
            movements_by_y[key] += value
        y = min(movements_by_y)
        x = movements_by_y[y]
        return x, y

    def _get_platforms_standing_on(self):
        return self._filter_sprites_standing_on(self._moving_platforms)

    def _filter_sprites_standing_on(self, group):
        colliding_sprites = self._collide(group)
        self.rect.y += 1
        sprites = self._collide(group)
        self.rect.y -= 1

        sprites_standing_on = []
        if not self._jumping:
            for platform in sprites:
                append = True
                for colliding_sprite in colliding_sprites:
                    if platform is colliding_sprite:
                        append = False
                if append:
                    sprites_standing_on.append(platform)

        return sprites_standing_on

    def _collide(self, group):
        return pygame.sprite.spritecollide(
            self, group, False, collided=collide_hitbox
        )

    def _jump(self, speed):
        self._v0 = speed
        self._y0 = self.rect.y
        self._t = 0
        self._jumping = True

    def _reset_jump(self):
        self._v0 = 0
        self._y0 = self.rect.y
        self._t = 0
        self._jumping = False

    def _move(self, new_pos):
        move(self.rect, new_pos, self._hittable_objects)
        if self.rect.y != new_pos[1]:
            self._reset_jump()


def uncollide_rect(rect, rect_last_move, hittable_objects):
    undo_y_movement(hittable_objects)
    rect.move_ip(0, -rect_last_move[1])

    crushed = uncollide_rect_x(rect, rect_last_move, hittable_objects)
    if crushed:
        return True

    redo_y_movement(hittable_objects)
    rect.move_ip(0, rect_last_move[1])

    crushed = uncollide_rect_y(rect, rect_last_move, hittable_objects)
    return crushed


def uncollide_rect_x(rect, rect_last_move, hittable_objects):
    old_rect = rect.copy()

    hit_list = rectcollide(rect, hittable_objects)
    collided_into_left_side = []
    collided_into_right_side = []
    for colliding_sprite in hit_list:
        colliding_sprite_last_move = get_last_move(colliding_sprite)
        relative_x_movement = colliding_sprite_last_move[0] - rect_last_move[0]
        if relative_x_movement > 0:
            collided_into_left_side.append(colliding_sprite)
        elif relative_x_movement < 0:
            collided_into_right_side.append(colliding_sprite)

    if bool(collided_into_left_side) and not bool(collided_into_right_side):
        uncollide(rect, collided_into_left_side, 'left')
    elif not bool(collided_into_left_side) and bool(collided_into_right_side):
        uncollide(rect, collided_into_right_side, 'right')

    crushed = (
        bool(collided_into_left_side) and bool(collided_into_right_side)
        or rectcollideany(rect, hittable_objects)
    )
    if crushed:
        rect = old_rect

    return False


def uncollide_rect_y(rect, rect_last_move, hittable_objects):
    old_rect = rect.copy()

    hit_list = rectcollide(rect, hittable_objects)
    collided_into_top_side = []
    collided_into_bottom_side = []
    for colliding_sprite in hit_list:
        colliding_sprite_last_move = get_last_move(colliding_sprite)
        relative_y_movement = colliding_sprite_last_move[1] - rect_last_move[1]
        if relative_y_movement > 0:
            collided_into_top_side.append(colliding_sprite)
        elif relative_y_movement < 0:
            collided_into_bottom_side.append(colliding_sprite)

    if bool(collided_into_top_side) and not bool(collided_into_bottom_side):
        uncollide(rect, collided_into_top_side, 'top')
    elif not bool(collided_into_top_side) and bool(collided_into_bottom_side):
        uncollide(rect, collided_into_bottom_side, 'bottom')

    crushed = (
        bool(collided_into_top_side) and bool(collided_into_bottom_side)
        or rectcollideany(rect, hittable_objects)
    )
    if crushed:
        rect = old_rect

    return crushed


def undo_y_movement(sprites):
    for sprite in sprites:
        last_move = get_last_move(sprite)
        get_hitbox(sprite).move_ip(0, -last_move[1])


def redo_y_movement(sprites):
    for sprite in sprites:
        last_move = get_last_move(sprite)
        get_hitbox(sprite).move_ip(0, last_move[1])


def get_last_move(sprite):
    last_move = 0, 0
    if hasattr(sprite, 'last_move'):
        last_move = sprite.last_move
    return last_move


def move(rect, new_pos, hittable_objects):
    move_x(rect, new_pos[0], hittable_objects)
    move_y(rect, new_pos[1], hittable_objects)


def move_x(rect, new_x, hittable_objects):
    old_x = rect.x
    rect.x = new_x
    hit_list = rectcollide(rect, hittable_objects)
    if rect.x < old_x:
        uncollide(rect, hit_list, 'left')
    elif rect.x > old_x:
        uncollide(rect, hit_list, 'right')


def move_y(rect, new_y, hittable_objects):
    old_y = rect.y
    rect.y = new_y
    hit_list = rectcollide(rect, hittable_objects)
    if rect.y < old_y:
        uncollide(rect, hit_list, 'top')
    elif rect.y > old_y:
        uncollide(rect, hit_list, 'bottom')


def uncollide(rect, colliding_sprites, collision_side):
    if not colliding_sprites:
        return
    if collision_side == 'left':
        rect.left = max(map(lambda tile: tile.rect.right, colliding_sprites))
    if collision_side == 'top':
        rect.top = max(map(lambda tile: tile.rect.bottom, colliding_sprites))
    if collision_side == 'right':
        rect.right = min(map(lambda tile: tile.rect.left, colliding_sprites))
    if collision_side == 'bottom':
        rect.bottom = min(map(lambda tile: tile.rect.top, colliding_sprites))


def rectcollide(rect, group):
    sprite = pygame.sprite.Sprite()
    sprite.rect = rect
    colliding_sprites = pygame.sprite.spritecollide(
        sprite, group, False, collided=collide_hitbox
    )
    return colliding_sprites


def rectcollideany(rect, group):
    sprite = pygame.sprite.Sprite()
    sprite.rect = rect
    colliding_sprites = pygame.sprite.spritecollideany(
        sprite, group, collided=collide_hitbox
    )
    return colliding_sprites


class Slash(pygame.sprite.Sprite):
    def __init__(self, frame_duration, flip):
        super().__init__()

        frames = load_images('slash')
        self._animation = Animation('slash', frames, frame_duration)

        self.image = self._animation.next()
        self._animation.reset()
        self._flip = flip
        if self._flip:
            self.image = pygame.transform.flip(self.image, True, False)
        self.rect = self.image.get_rect()

    def update(self):
        if self._animation.is_at_end():
            self.kill()
            return
        self.image = self._animation.next()
        if self._flip:
            self.image = pygame.transform.flip(self.image, True, False)


class Snake(pygame.sprite.Sprite):
    def __init__(self, x_movement_start, x_movement_end, rect_bottom):
        super().__init__()

        self._idle_image = load_image('snake.png')
        self._walk_animation = Animation(
            'walk', load_images('snake_walk'), 10, cycle=True
        )

        self.image = self._idle_image
        self._flip = False
        self.hitbox = pygame.Rect(0, 0, 16, 14)
        self.hitbox.bottomleft = x_movement_start, rect_bottom
        self.rect = self.image.get_rect()
        self._update_rect()

        movement_range = abs(x_movement_start - x_movement_end)
        self._max_walk_distance = movement_range - self.hitbox.width
        self._walk_distance = 0

    def update(self):
        speed = 1

        self._walk_distance += speed
        if self._walk_distance >= self._max_walk_distance:
            self._flip = not self._flip
            self._walk_distance = speed

        if not self._flip:
            x_movement = speed
        else:
            x_movement = -speed
        self.hitbox.x += x_movement

        self.image = self._walk_animation.next()
        if self._flip:
            self.image = pygame.transform.flip(self.image, True, False)

        self._update_rect()

    def _update_rect(self):
        offset = (-8, -18)
        self.rect.topleft = self.hitbox.topleft
        self.rect.move_ip(offset)


def collide_hitbox(sprite, other):
    hitbox1 = get_hitbox(sprite)
    hitbox2 = get_hitbox(other)
    return hitbox1.colliderect(hitbox2)


def get_hitbox(sprite):
    return sprite.hitbox if hasattr(sprite, 'hitbox') else sprite.rect


class Animation:
    def __init__(self, name, frames, frame_duration, cycle=False):
        self.name = name
        self.frame_duration = frame_duration
        self.next_index = 0

        self._frames = []
        for frame in frames:
            self._frames.extend(itertools.repeat(frame, times=frame_duration))

        self._cycle = cycle

    def __getitem__(self, i):
        return self._frames[i]

    def __len__(self):
        return len(self._frames)

    def next(self):
        if self._cycle and self.next_index >= len(self._frames):
            self.next_index = 0
        self.next_index += 1
        return self._frames[self.next_index - 1]

    def is_at_end(self):
        return self.next_index == len(self._frames) and not self._cycle

    def reset(self):
        self.next_index = 0


class DoorTextViewer:
    def __init__(self, player, level_completions):
        self._player = player
        self._level_completions = level_completions
        self._font_renderer = FontRenderer()

    def draw(self, surface):
        door = self._player.choose_door_to_walk_in()
        if door:
            text = 'LEVEL ' + str(door.destination_level)
            rect = self._font_renderer.calculate_rect(text)
            rect.midtop = WIDTH // 2, 32
            self._font_renderer.draw(surface, rect.topleft, text)

            if self._level_completions[door.destination_level].completed:
                text2 = '(COMPLETED)'
                rect2 = self._font_renderer.calculate_rect(text2)
                rect2.midtop = rect.centerx, rect.bottom
                self._font_renderer.draw(surface, rect2.topleft, text2)


class Camera:
    def __init__(self):
        self.offset = 0, 0

    def follow(self, sprite):
        hitbox = get_hitbox(sprite)
        x = (WIDTH - hitbox.width) // 2 - hitbox.x
        y = (HEIGHT - hitbox.height) // 2 - hitbox.y
        self.offset = x, y

    def rect_view(self):
        return pygame.Rect((-self.offset[0], -self.offset[1]), SIZE)


class CameraSurface(pygame.Surface):
    def __init__(self, camera, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.camera_mode = True
        self._camera = camera

    def blit(self, source, dest, area=None, special_flags=0):
        if not self.camera_mode:
            return super().blit(source, dest, area, special_flags)
        new_dest = self._adjust_dest(dest)
        return super().blit(source, new_dest, area, special_flags)

    def blits(self, blit_sequence, doreturn=1):
        if not self.camera_mode:
            return super().blits(blit_sequence, doreturn)
        new_blit_sequence = []
        for blit in blit_sequence:
            new_blit = (blit[0], self._adjust_dest(blit[1])) + blit[2:]
            new_blit_sequence.append(new_blit)
        return super().blits(new_blit_sequence, doreturn)

    def _adjust_dest(self, dest):
        coordinates = dest.topleft if isinstance(dest, pygame.Rect) else dest
        x = coordinates[0] + self._camera.offset[0]
        y = coordinates[1] + self._camera.offset[1]
        return x, y


@dataclasses.dataclass
class Level:
    background_tiles: pygame.sprite.Group()
    endless_background_renderers: list
    tiles: pygame.sprite.Group
    doors: pygame.sprite.Group
    snakes: pygame.sprite.Group
    moving_platforms: pygame.sprite.Group
    water_level: int

    def get_hittable_objects(self):
        hittable_objects = pygame.sprite.Group()
        hittable_objects.add((self.tiles, self.moving_platforms))
        return hittable_objects


def create_level(level_number, camera):
    level_data = levels.get_level_data(level_number)

    bg_tiles_str = level_data.background_tiles_str
    background_tiles = tiles_from_str(bg_tiles_str, background=True)

    endless_background_renderers = create_endless_background_renderers(
        bg_tiles_str, camera
    )

    # tile_images = {
    #     'a': create_tile_image('a_background'),
    #     'b': create_tile_image('b_background'),
    #     'c': create_tile_image('c_background'),
    #     'd': create_tile_image('d_background'),
    #     'e': create_tile_image('e_background'),
    #     'f': create_tile_image('f_background'),
    #     'g': create_tile_image('g_background'),
    #     'h': create_tile_image('h_background'),
    #     'q': create_tile_image('q_background'),
    #     'r': create_tile_image('r_background'),
    #     's': create_tile_image('s_background'),
    #     't': create_tile_image('t_background'),
    #     'u': create_tile_image('u_background'),
    #     'v': create_tile_image('v_background'),
    #     'w': create_tile_image('w_background'),
    # }
    # def func_choose_tile(i):
    #     if i == 0:
    #         return 'a'
    #     else:
    #         if math.log2(i).is_integer():
    #             return 'r'
    #         else:
    #             return 'q'
    # def func_choose_tile_grid(x, y):
    #     if (x, y) == (0, 0):
    #         return 'a'
    #     else:
    #         if (x != 0 and math.log2(x).is_integer()) or y % 2 == 0:
    #             return 'r'
    #         else:
    #             return 'q'
    # if level_number == 2:
    #     endless_background_renderers.extend([
    #         EndlessLineOfTilesRenderer((58, 12), (0, -1), camera, tile_images, func_choose_tile),
    #         EndlessLineOfTilesRenderer((59, -2), (0, 1), camera, tile_images, func_choose_tile),
    #         EndlessLineOfTilesRenderer((55, 5), (-1, 0), camera, tile_images, func_choose_tile),
    #         EndlessLineOfTilesRenderer((61, 5), (1, 0), camera, tile_images, func_choose_tile),
    #         EndlessGridOfTilesRenderer((55, 3), -1, -1, camera, tile_images, func_choose_tile_grid),
    #         EndlessGridOfTilesRenderer((55, 7), -1, 1, camera, tile_images, func_choose_tile_grid),
    #         EndlessGridOfTilesRenderer((61, 3), 1, -1, camera, tile_images, func_choose_tile_grid),
    #         EndlessGridOfTilesRenderer((61, 7), 1, 1, camera, tile_images, func_choose_tile_grid),
    #     ])

    tiles = tiles_from_str(level_data.tiles_str)

    doors = pygame.sprite.Group()
    for door_data in level_data.doors:
        door = Door(door_data.destination_level, door_data.start)
        x = door_data.x * TILE_SIZE
        y = (door_data.y + 1) * TILE_SIZE
        door.rect.bottomleft = x, y
        doors.add(door)

    snakes = pygame.sprite.Group()
    for snake_data in level_data.snakes:
        x_movement_start = snake_data.x_movement_start_end[0] * TILE_SIZE
        x_movement_end = snake_data.x_movement_start_end[1] * TILE_SIZE
        rect_bottom = (snake_data.y + 1) * TILE_SIZE
        snakes.add(Snake(x_movement_start, x_movement_end, rect_bottom))

    moving_platforms = pygame.sprite.Group()
    for moving_platform_data in level_data.moving_platforms:
        tiles_str = moving_platform_data.tiles_str
        destinations = moving_platform_data.destinations
        moving_platforms.add(MovingPlatform(tiles_str, destinations))

    # # TEMP
    # if level_number == 0:
    #     tile = Tile('g3', (0, 9))
    #     tile.rect.move_ip(1, 0)
    #     tiles.add(tile)
    #     tile = Tile('g3', (2, 7))
    #     tile.rect.move_ip(0, -1)
    #     tiles.add(tile)
    #     tile = Tile('g3', (3, 8))
    #     tiles.add(tile)
    #     tile = Tile('g3', (3, 9))
    #     tile.rect.move_ip(-1, 0)
    #     tiles.add(tile)

    water_level = level_data.tiles_str.count('\n') * TILE_SIZE

    return Level(
        background_tiles, endless_background_renderers, tiles, doors, snakes,
        moving_platforms, water_level
    )


def create_endless_background_renderers(background_tiles_str, camera):
    renderers_list = []
    for y, line in enumerate(background_tiles_str.splitlines()):
        for x, char in enumerate(line):
            # sides_list = []
            # if x == 0:
            #     sides_list.append('left')
            # if x == len(line) - 1:
            #     sides_list.append('right')
            # if y == 0:
            #     sides_list.append('top')
            # if (x, y) == (0, 0):
            #     side_list.append('topleft')
            # if (x, y) == (len(line) - 1, 0):
            #     side_list.append('topright')

            # for side in sides_list:
            #     r = create_endless_background_renderer_for_tile(
            #         (x, y), char, side, camera
            #     )
            #     if r is not None:
            #         renderers.append(r)

            if x == 0:
                adjacent_tile = choose_adjacent_tiles(char)['left']
                if adjacent_tile != '-':
                    tile_images_dict = create_tile_images_dict(adjacent_tile)
                    renderers_list.append(EndlessLineOfTilesRenderer(
                        (-1, y), (-1, 0), camera, tile_images_dict
                    ))
            if x == len(line) - 1:
                adjacent_tile = choose_adjacent_tiles(char)['right']
                if adjacent_tile != '-':
                    tile_images_dict = create_tile_images_dict(adjacent_tile)
                    renderers_list.append(EndlessLineOfTilesRenderer(
                        (len(line), y), (1, 0), camera, tile_images_dict
                    ))
            if y == 0:
                adjacent_tile = choose_adjacent_tiles(char)['top']
                if adjacent_tile != '-':
                    tile_images_dict = create_tile_images_dict(adjacent_tile)
                    renderers_list.append(EndlessLineOfTilesRenderer(
                        (x, -1), (0, -1), camera, tile_images_dict
                    ))
            if (x, y) == (0, 0):
                adjacent_tile_top = choose_adjacent_tiles(char)['top']
                adjacent_tile_left = choose_adjacent_tiles(char)['left']
                if (
                    choose_adjacent_tiles(adjacent_tile_top)['left']
                    == choose_adjacent_tiles(adjacent_tile_left)['top']
                    == 'q'
                ):
                    tile_images_dict = create_tile_images_dict('q')
                    renderers_list.append(EndlessGridOfTilesRenderer(
                        (-1, -1), -1, -1, camera, tile_images_dict
                    ))
            if (x, y) == (len(line) - 1, 0):
                adjacent_tile_top = choose_adjacent_tiles(char)['top']
                adjacent_tile_right = choose_adjacent_tiles(char)['right']
                if (
                    choose_adjacent_tiles(adjacent_tile_top)['right']
                    == choose_adjacent_tiles(adjacent_tile_right)['top']
                    == 'q'
                ):
                    tile_images_dict = create_tile_images_dict('q')
                    renderers_list.append(EndlessGridOfTilesRenderer(
                        (len(line), -1), 1, -1, camera, tile_images_dict
                    ))

#         leftmost = line[0]
#         if leftmost != '-':
#             left_line_renderer = create_renderer_endless_line_of_bg_tiles(
#                 (0, y), leftmost, 'left', camera
#             )
#             renderers_list.append(left_line_renderer)

#         rightmost = line[-1]
#         if rightmost != '-':
#             right_line_renderer = create_renderer_endless_line_of_bg_tiles(
#                 (len(line) - 1, y), rightmost, 'right', camera
#             )
#             renderers_list.append(right_line_renderer)

#         if y == 0:
#             for x, char in enumerate(line):
#                 if char != '-':
#                     top_line_renderer = create_renderer_endless_line_of_bg_tiles(
#                         (x, y), char, 'top', camera
#                     )
#                     renderers_list.append(top_line_renderer)

#             left_grid_renderer = EndlessGridOfTilesRenderer(
#                 (-1, -1), -1, -1, camera, tile_images_dict)

    return renderers_list


def create_tile_images_dict(tile_char):
    tile_type = tile_char + '_background'
    return {0: create_tile_image(tile_type)}


# def create_endless_background_renderer_for_tile(
#     tile_coordinates, tile_char, side, camera
# ):
#     renderer = None

#     if side in ('left', 'top', 'right'):
#         increment = 0, 0
#         if side == 'left':
#             increment = -1, 0
#         elif side == 'top':
#             increment = 0, -1
#         elif side == 'right':
#             increment = 1, 0

#         start = (
#             tile_coordinates[0] + increment[0],
#             tile_coordinates[1] + increment[1]
#         )

#         adjacent_tile = choose_adjacent_tiles(tile_char)[side]
#         if adjacent_tile != '-':
#             tile_images_dict = {
#                 0: create_tile_image(adjacent_tile)
#             }
#             renderer = EndlessLineOfTilesRenderer(
#                 start, increment, camera, tile_images_dict
#             )
#     elif side in ('topleft', 'topright'):
#         if side == 'topleft':
#             increment_x = -1
#             increment_y = -1
#         elif side == 'topright':
#             increment_x = 1
#             increment_y = -1

#         start = (
#             tile_coordinates[0] + increment_x,
#             tile_coordinates[1] + increment_y
#         )

#         tile_images_dict = {
#             0: create_tile_image('q')
#         }

#         if side == 'topleft':
#             adjacent_tile_top = choose_adjacent_tiles(tile_char)['top']
#             adjacent_tile_left = choose_adjacent_tiles(tile_char)['left']
#             if (
#                 choose_adjacent_tiles(adjacent_tile_top)['left']
#                 == choose_adjacent_tiles(adjacent_tile_left)['top']
#                 == 'q'
#             ):
#                 renderer = EndlessGridOfTilesRenderer(
#                     start, increment_x, increment_y, camera, tile_images_dict
#                 )
#         elif side == 'topright':
#             adjacent_tile_top = choose_adjacent_tiles(tile_char)['top']
#             adjacent_tile_right = choose_adjacent_tiles(tile_char)['right']
#             if (
#                 choose_adjacent_tiles(adjacent_tile_top)['right']
#                 == choose_adjacent_tiles(adjacent_tile_right)['top']
#                 == 'q'
#             ):
#                 renderer = EndlessGridOfTilesRenderer(
#                     start, increment_x, increment_y, camera, tile_images_dict
#                 )

#     return renderer


# def create_renderer_endless_line_of_bg_tiles(
#     tile_coordinates, tile_char, side, camera
# ):
#     increment = 0, 0
#     if side == 'left':
#         increment = -1, 0
#     elif side == 'top':
#         increment = 0, -1
#     elif side == 'right':
#         increment = 1, 0

#     start = (
#         tile_coordinates[0] + increment[0],
#         tile_coordinates[1] + increment[1]
#     )

#     adjacent_tile = choose_adjacent_tiles(tile_char)[side]
#     tile_images_dict = {
#         0: create_tile_image(adjacent_tile)
#     }

#     return EndlessLineOfTilesRenderer(
#         start, increment, camera, tile_images_dict
#     )


def tiles_from_str(tiles_str, background=False):
    tiles = pygame.sprite.Group()
    for y, line in enumerate(tiles_str.splitlines()):
        for x, tile_char in enumerate(line):
            if tile_char != '-':
                bg_left = None
                bg_right = None
                if not background:
                    neighbour_left = '-'
                    if x - 1 >= 0:
                        neighbour_left = line[x-1]
                    neighbour_right = '-'
                    if x + 1 < len(line):
                        neighbour_right = line[x+1]
                    bg_left_char, bg_right_char = choose_background_for_tile(
                        neighbour_left, neighbour_right
                    )
                    bg_left = tile_char_to_tile_type(bg_left_char)
                    bg_right = tile_char_to_tile_type(bg_right_char)
                tile_type = tile_char_to_tile_type(tile_char, background)
                tile_image = create_tile_image(tile_type, bg_left, bg_right)
                tiles.add(Tile((x, y), tile_image))
    return tiles


def choose_background_for_tile(neighbour_left, neighbour_right):
    bg_left = choose_adjacent_tiles(neighbour_left)['right']
    bg_right = choose_adjacent_tiles(neighbour_right)['left']
    return bg_left, bg_right


def tile_char_to_tile_type(tile_char, background=False):
    if tile_char == '-':
        tile_type = None
    elif background:
        tile_type = tile_char + '_background'
    else:
        tile_type = tile_char.lower()
        if tile_char.islower():
            tile_type += '_dirt'
        elif tile_char.isupper():
            tile_type += '_stone'
    return tile_type


def choose_adjacent_tiles(tile_char):
    neighbour_left_map = {
        '0': '0',
        '1': '0',
        '2': '2',
        'a': '-',
        'b': '-',
        'c': 'c',
        'd': 'c',
        'e': 'q',
        'f': 'g',
        'g': 'g',
        'h': '-',
        'i': '-',
        'j': '-',
        'k': '-',
        'l': '-',
        'm': 'c',
        'n': 'n',
        'o': 'n',
        'p': 'n',
        'q': 'q',
        'r': 'q',
        's': 'q',
        't': 'q',
        'u': 'g',
        'v': 'c',
        'w': 'q',
        '-': '-',
    }
    left = translate_tile_char(tile_char, neighbour_left_map)

    neighbour_top_map = {
        '0': '0',
        '1': '0',
        '2': '-',
        'a': 'a',
        'b': '-',
        'c': '-',
        'd': '-',
        'e': 'e',
        'f': 'e',
        'g': 'q',
        'h': 'a',
        'i': '-',
        'j': 'j',
        'k': 'j',
        'l': '-',
        'm': '-',
        'n': '-',
        'o': '-',
        'p': '-',
        'q': 'q',
        'r': 'q',
        's': 'q',
        't': 'q',
        'u': 'q',
        'v': 'a',
        'w': 'e',
        '-': '-',
    }
    top = translate_tile_char(tile_char, neighbour_top_map)

    neighbour_right_map = {
        '0': '0',
        '1': '0',
        '2': '2',
        'a': 'q',
        'b': 'c',
        'c': 'c',
        'd': '-',
        'e': '-',
        'f': '-',
        'g': 'g',
        'h': 'g',
        'i': '-',
        'j': '-',
        'k': '-',
        'l': 'n',
        'm': 'n',
        'n': 'n',
        'o': 'c',
        'p': '-',
        'q': 'q',
        'r': 'q',
        's': 'q',
        't': 'g',
        'u': 'q',
        'v': 'q',
        'w': 'c',
        '-': '-',
    }
    right = translate_tile_char(tile_char, neighbour_right_map)

    return {
        'left': left,
        'top': top,
        'right': right,
    }


def translate_tile_char(tile_char, translation_map):
    new_tile_char = translation_map[tile_char.lower()]
    if tile_char.isupper():
        new_tile_char = new_tile_char.upper()
    return new_tile_char


@dataclasses.dataclass
class World:
    level: Level
    player: Player
    door_text_viewer: DoorTextViewer
    water_tiles: pygame.sprite.Group


def create_world(level_number, prev_level_number, level_completions, camera):
    level = create_level(level_number, camera)
    starting_door = choose_door_to_start_at(level, prev_level_number)
    player = Player(starting_door.rect.midbottom, level)
    door_text_viewer = DoorTextViewer(player, level_completions)
    water_tiles = water(level.water_level, camera)
    return World(level, player, door_text_viewer, water_tiles)


def choose_door_to_start_at(level, prev_level_number):
    doors = []
    for door in level.doors:
        if door.destination_level == prev_level_number and door.start:
            doors.append(door)
    return doors[0]


def water(water_level, camera):
    tile_water_level = water_level / TILE_SIZE
    water_tiles = pygame.sprite.Group()
    tile_count = math.ceil(WIDTH / TILE_SIZE) + 1
    for tile_x in range(tile_count):
        tile_coordinates = tile_x, tile_water_level
        tile_image = create_tile_image('2')
        tile = WaterTileTop(tile_coordinates, tile_image, tile_count, camera)
        water_tiles.add(tile)

    tile_count_horizontal = tile_count
    tile_count_horizontal = ceil_base(tile_count_horizontal, base=2)
    tile_count_vertical = math.ceil(HEIGHT / TILE_SIZE) + 1
    tile_count_vertical = ceil_base(tile_count_vertical, base=2)
    for tile_x in range(tile_count_horizontal):
        for tile_y in range(tile_count_vertical):
            tile_type = '0'
            if tile_y % 2 == tile_x % 2:
                tile_type = '1'
            tile_coordinates = tile_x, tile_water_level + 1 + tile_y
            tile_image = create_tile_image(tile_type)
            tile_counts = tile_count_horizontal, tile_count_vertical
            tile = WaterTileMiddle(
                tile_coordinates, tile_image, *tile_counts, camera
            )
            water_tiles.add(tile)

    return water_tiles


def ceil_base(x, base=1):
    return math.ceil(x / base) * base


class Tile(pygame.sprite.Sprite):
    def __init__(self, tile_coordinates, tile_image):
        super().__init__()

        self.image = tile_image
        self.rect = self.image.get_rect()
        self.rect.x = tile_coordinates[0] * TILE_SIZE
        self.rect.y = tile_coordinates[1] * TILE_SIZE


def create_tile_image(
    tile_type, bg_left_tile_type=None, bg_right_tile_type=None
):
    image = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
    if bg_left_tile_type is not None:
        area = 0, 0, TILE_SIZE // 2, TILE_SIZE
        bg_left_image = load_tile_image(bg_left_tile_type)
        image.blit(bg_left_image, (0, 0), area)
    if bg_right_tile_type is not None:
        area = TILE_SIZE // 2, 0, TILE_SIZE // 2, TILE_SIZE
        bg_right_image = load_tile_image(bg_right_tile_type)
        image.blit(bg_right_image, (TILE_SIZE // 2, 0), area)
    foreground_image = load_tile_image(tile_type)
    image.blit(foreground_image, (0, 0))
    return image


def load_tile_image(tile_type):
    image_filename = 'tiles/' + tile_type + '.png'
    return load_image(image_filename)


class WaterTileTop(Tile):
    def __init__(self, tile_coordinates, tile_image, tile_count, camera):
        super().__init__(tile_coordinates, tile_image)

        self._camera = camera
        self._right_start = self.rect.right
        self._right_step = tile_count * TILE_SIZE

    def update(self):
        view = self._camera.rect_view()
        right = least_multiple(self._right_start, self._right_step, view.x + 1)
        self.rect.right = right


class WaterTileMiddle(WaterTileTop):
    def __init__(
        self, tile_coordinates, tile_image, tile_count_horizontal,
        tile_count_vertical, camera
    ):
        super().__init__(
            tile_coordinates, tile_image, tile_count_horizontal, camera
        )

        self._camera = camera
        self._bottom_start = self.rect.bottom
        self._bottom_step = tile_count_vertical * TILE_SIZE

    def update(self):
        super().update()

        view = self._camera.rect_view()
        bottom_min = max(view.y + 1, self._bottom_start)
        bottom = least_multiple(
            self._bottom_start, self._bottom_step, bottom_min
        )
        self.rect.bottom = bottom


# class EndlessLineOfTilesRenderer:
#     def __init__(
#         self, start, increment, tile_images, func_choose_tile, camera
#     ):
#         self._start_coordinates = start
#         self._increment = increment
#         self._tile_images = tile_images
#         self._choose_tile = func_choose_tile
#         self._camera = camera

#     def draw(self, surface):
#         # horizontal = self._increment[0] != 0

#         # if horizontal:
#         #     tile_count = math.ceil(WIDTH / TILE_SIZE)
#         # else:
#         #     tile_count = math.ceil(HEIGHT / TILE_SIZE)

#         # step = tile_count

#         # for origin in range(tile_count):
#         #     if self._increment[0] == -1:
#         #         rightmost_visible_tile = self._camera.rect_view().right // TILE_SIZE
#         #         max_tile_x = min(rightmost_visible_tile, self._start_coordinates[0])
#         #         x = greatest_multiple(origin, step, max_tile_x)
#         #         index = x - origin
#         #     elif self._increment[0] == 1:
#         #         leftmost_visible_tile = self._camera.rect_view().left // TILE_SIZE
#         #         min_tile_x = max(leftmost_visible_tile, self._start_coordinates[0])
#         #         x = least_multiple(origin, step, min_tile_x)
#         #         index = x - origin
#         #     elif self._increment[1] == -1:
#         #         lowest_visible_tile = self._camera.rect_view().bottom // TILE_SIZE
#         #         max_tile_y = min(lowest_visible_tile, self._start_coordinates[1])
#         #         y = greatest_multiple(origin, step, max_tile_y)
#         #         index = y - origin
#         #     elif self._increment[1] == 1:
#         #         highest_visible_tile = self._camera.rect_view().top // TILE_SIZE
#         #         min_tile_y = max(highest_visible_tile, self._start_coordinates[1])
#         #         y = least_multiple(origin, step, min_tile_y)
#         #         index = y - origin

#         # camera_view = self._camera.rect_view()

#         # if horizontal:
#         #     tile_count = math.ceil(WIDTH / TILE_SIZE)
#         #     increment = self._increment[0]
#         #     if increment == -1:
#         #         first_visible_tile = camera_view.right // TILE_SIZE
#         #     elif increment == 1:
#         #         first_visible_tile = camera_view.left // TILE_SIZE
#         # else:
#         #     tile_count = math.ceil(HEIGHT / TILE_SIZE)
#         #     increment = self._increment[1]
#         #     if increment == -1:
#         #         first_visible_tile = camera_view.bottom // TILE_SIZE
#         #     elif increment == 1:
#         #         first_visible_tile = camera_view.top // TILE_SIZE

#         # if horizontal:
#         #     first_tile_in_line = self._start_coordinates[0]
#         # else:
#         #     first_tile_in_line = self._start_coordinates[1]

#         # step = tile_count

#         # for origin in range(tile_count):
#         #     if increment == -1:
#         #         max_tile_coordinate = min(first_visible_tile, first_tile_in_line)
#         #         tile_coordinate = greatest_multiple(origin, step, max_tile_coordinate)
#         #     elif increment == 1:
#         #         min_tile_coordinate = max(first_visible_tile, first_tile_in_line)
#         #         tile_coordinate = least_multiple(origin, step, min_tile_coordinate)

#         #     if horizontal:
#         #         coordinates = self._start_coordinates[0], tile_coordinate
#         #     else:
#         #         coordinates = tile_coordinate, self._start_coordinates[1]

#         #     if horizontal:
#         #         if increment == -1:
#         #             index = origin - tile_coordinate
#         #         elif increment == 1:
#         #             index = tile_coordinate - origin
#         #     else:
#         #     image = self._tile_images[self._choose_tile(index)]
#         #     tile = Tile(coordinates, image)
#         #     surface.blit(tile.image, tile.rect)

#         # camera_view = self._camera.rect_view()
#         # if horizontal:
#         #     tile_count = math.ceil(WIDTH / TILE_SIZE)
#         # else:
#         #     tile_count = math.ceil(HEIGHT / TILE_SIZE)
#         # step = tile_count

#         # for origin in range(tile_count):
#         #     if self._increment[0] == -1:
#         #         rightmost_visible_tile = camera_view.right // TILE_SIZE
#         #         first_tile_in_line = self._start_coordinates[0]
#         #         max_tile_x = min(rightmost_visible_tile, first_tile_in_line)
#         #         x = greatest_multiple(origin, step, max_tile_x)
#         #         tile_coordinates = x, self._start_coordinates[1]
#         #         index = self._start_coordinates[0] - x
#         #     elif self._increment[0] == 1:
#         #         leftmost_visible_tile = camera_view.left // TILE_SIZE
#         #         first_tile_in_line = self._start_coordinates[0]
#         #         min_tile_x = max(leftmost_visible_tile, first_tile_in_line)
#         #         x = least_multiple(origin, step, min_tile_x)
#         #         tile_coordinates = x, self._start_coordinates[1]
#         #         index = x - self._start_coordinates[0]
#         #     elif self._increment[1] == -1:
#         #         lowest_visible_tile = camera_view.bottom // TILE_SIZE
#         #         first_tile_in_line = self._start_coordinates[1]
#         #         max_tile_y = min(lowest_visible_tile, first_tile_in_line)
#         #         y = greatest_multiple(origin, step, max_tile_y)
#         #         tile_coordinates = self._start_coordinates[0], y
#         #         index = self._start_coordinates[1] - y
#         #     elif self._increment[1] == 1:
#         #         highest_visible_tile = camera_view.top // TILE_SIZE
#         #         first_tile_in_line = self._start_coordinates[1]
#         #         min_tile_y = max(highest_visible_tile, first_tile_in_line)
#         #         y = least_multiple(origin, step, min_tile_y)
#         #         tile_coordinates = self._start_coordinates[0], y
#         #         index = y - self._start_coordinates[1]

#         #     image = self._tile_images[self._choose_tile(index)]
#         #     tile = Tile(tile_coordinates, image)
#         #     surface.blit(tile.image, tile.rect)

#         if self._increment == (-1, 0):
#             min_tile_x = self._camera.rect_view().left // TILE_SIZE
#             if self._start_coordinates[0] >= min_tile_x:
#                 max_tile_x = self._camera.rect_view().right // TILE_SIZE
#                 max_tile_x = min(max_tile_x, self._start_coordinates[0])
#                 for x in range(min_tile_x, max_tile_x + 1):
#                     coordinates = x, self._start_coordinates[1]
#                     relative_i = self._start_coordinates[0] - x
#                     image = self._tile_images[self._choose_tile(relative_i)]
#                     tile = Tile(coordinates, image)
#                     surface.blit(tile.image, tile.rect)
#         elif self._increment == (1, 0):
#             max_tile_x = self._camera.rect_view().right // TILE_SIZE
#             if self._start_coordinates[0] <= max_tile_x:
#                 min_tile_x = self._camera.rect_view().left // TILE_SIZE
#                 min_tile_x = max(min_tile_x, self._start_coordinates[0])
#                 for x in range(min_tile_x, max_tile_x + 1):
#                     coordinates = x, self._start_coordinates[1]
#                     relative_i = x - self._start_coordinates[0]
#                     image = self._tile_images[self._choose_tile(relative_i)]
#                     tile = Tile(coordinates, image)
#                     surface.blit(tile.image, tile.rect)
#         elif self._increment == (0, -1):
#             min_tile_y = self._camera.rect_view().top // TILE_SIZE
#             if self._start_coordinates[1] >= min_tile_y:
#                 max_tile_y = self._camera.rect_view().bottom // TILE_SIZE
#                 max_tile_y = min(max_tile_y, self._start_coordinates[1])
#                 for y in range(min_tile_y, max_tile_y + 1):
#                     coordinates = self._start_coordinates[0], y
#                     relative_i = self._start_coordinates[1] - y
#                     image = self._tile_images[self._choose_tile(relative_i)]
#                     tile = Tile(coordinates, image)
#                     surface.blit(tile.image, tile.rect)
#         elif self._increment == (0, 1):
#             max_tile_y = self._camera.rect_view().bottom // TILE_SIZE
#             if self._start_coordinates[1] <= max_tile_y:
#                 min_tile_y = self._camera.rect_view().top // TILE_SIZE
#                 min_tile_y = max(min_tile_y, self._start_coordinates[1])
#                 for y in range(min_tile_y, max_tile_y + 1):
#                     coordinates = self._start_coordinates[0], y
#                     relative_i = y - self._start_coordinates[1]
#                     image = self._tile_images[self._choose_tile(relative_i)]
#                     tile = Tile(coordinates, image)
#                     surface.blit(tile.image, tile.rect)

#         # if self._increment[0] == -1:
#         #     min_tile_x = camera_view.left // TILE_SIZE
#         #     if self._start_coordinates[0] >= min_tile_x:
#         #         max_tile_x = camera_view.right // TILE_SIZE
#         #         max_tile_x = min(max_tile_x, self._start_coordinates[0])
#         #         first_tile_coordinates = max_tile_x, self._start_coordinates[1]
#         #         length = max_tile_x - min_tile_x + 1
#         #         self._draw_line_of_tiles(surface, first_tile_coordinates, length)
#         # elif self._increment[0] == 1:
#         #     max_tile_x = camera_view.left // TILE_SIZE
#         #     if self._start_coordinates[0] >= max_tile_x:
#         #         min_tile_x = camera_view.right // TILE_SIZE
#         #         min_tile_x = max(min_tile_x, self._start_coordinates[0])
#         #         first_tile_coordinates = min_tile_x, self._start_coordinates[1]
#         #         length = max_tile_x - min_tile_x + 1
#         #         self._draw_line_of_tiles(surface, first_tile_coordinates, length)
#         # elif self._increment[1] == -1:
#         #     pass
#         # elif self._increment[1] == 1:
#         #     pass

#         # if horizontal:
#         #     tile_count = math.ceil(WIDTH / TILE_SIZE)
#         #     step = tile_count
#         #     for origin in range(tile_count):
#         #         if self._increment[0] == -1:
#         #             rightmost_visible_tile = self._camera.rect_view().right // TILE_SIZE
#         #             max_tile_x = min(rightmost_visible_tile, self._start_coordinates[0])
#         #             x = greatest_multiple(origin, step, max_tile_x)
#         #             index = x - origin
#         #         elif self._increment[0] == 1:
#         #             min_value_pixels = self._camera.rect_view().
#         # else:
#         #     tile_count = math.ceil(HEIGHT / TILE_SIZE)
#         #     start = self._start_coordinates[1]
#         #     step = self._start_coordinates[1]

#         # image = self._tile_images[self._choose_tile(index)]
#         # tile = Tile((x, self._increment[1]), image)
#         # surface.blit(tile.image, tile.rect)

#     # def _draw_line_of_tiles(self, surface, first_tile_coordinates, length):
#     #     tile_coordinates = first_tile_coordinates

#     #     for relative_index in range(length):
#     #         image = self._tile_images[self._choose_tile(relative_index)]
#     #         tile = Tile(tile_coordinates, image)
#     #         surface.blit(tile.image, tile.rect)
#     #         tile_coordinates = (
#     #             tile_coordinates[0] + self._increment[0],
#     #             tile_coordinates[1] + self._increment[1]
#     #         )

#     # def _draw_tile(self, first_tile_coordinates, relative_index):
#     #     tile_coordinates = first_tile_coordinates
#     #     for i in range(relative_index - 1):
#     #         tile_coordinates = (
#     #             tile_coordinates[0] + self._increment[0],
#     #             tile_coordinates[1] + self._increment[1]
#     #         )
#     #     image = self._choose_tile(relative_index)
#     #     tile = Tile(tile_coordinates, image)
#     #     surface.blit(tile.image, tile.rect)


def least_multiple(origin, step, min_value):
    step = abs(step)
    return origin + math.ceil((min_value - origin) / step) * step


# # def greatest_multiple(origin, step, max_value):
# #     step = -abs(step)
# #     return origin + math.ceil((max_value - origin) / step) * step


# class EndlessLineOfTilesRenderer:
#     def __init__(
#         self, start, increment, tile_images, func_choose_tile, camera
#     ):
#         self._start_coordinates = start
#         self._increment = increment
#         self._tile_images = tile_images
#         self._choose_tile = func_choose_tile
#         self._camera = camera

#     def draw(self, surface):
#         # horizontal = self._increment[0] != 0

#         # if horizontal:
#         #     tile_count = math.ceil(WIDTH / TILE_SIZE)
#         # else:
#         #     tile_count = math.ceil(HEIGHT / TILE_SIZE)

#         # step = tile_count

#         # for origin in range(tile_count):
#         #     if self._increment[0] == -1:
#         #         rightmost_visible_tile = self._camera.rect_view().right // TILE_SIZE
#         #         max_tile_x = min(rightmost_visible_tile, self._start_coordinates[0])
#         #         x = greatest_multiple(origin, step, max_tile_x)
#         #         index = x - origin
#         #     elif self._increment[0] == 1:
#         #         leftmost_visible_tile = self._camera.rect_view().left // TILE_SIZE
#         #         min_tile_x = max(leftmost_visible_tile, self._start_coordinates[0])
#         #         x = least_multiple(origin, step, min_tile_x)
#         #         index = x - origin
#         #     elif self._increment[1] == -1:
#         #         lowest_visible_tile = self._camera.rect_view().bottom // TILE_SIZE
#         #         max_tile_y = min(lowest_visible_tile, self._start_coordinates[1])
#         #         y = greatest_multiple(origin, step, max_tile_y)
#         #         index = y - origin
#         #     elif self._increment[1] == 1:
#         #         highest_visible_tile = self._camera.rect_view().top // TILE_SIZE
#         #         min_tile_y = max(highest_visible_tile, self._start_coordinates[1])
#         #         y = least_multiple(origin, step, min_tile_y)
#         #         index = y - origin

#         # camera_view = self._camera.rect_view()

#         # if horizontal:
#         #     tile_count = math.ceil(WIDTH / TILE_SIZE)
#         #     increment = self._increment[0]
#         #     if increment == -1:
#         #         first_visible_tile = camera_view.right // TILE_SIZE
#         #     elif increment == 1:
#         #         first_visible_tile = camera_view.left // TILE_SIZE
#         # else:
#         #     tile_count = math.ceil(HEIGHT / TILE_SIZE)
#         #     increment = self._increment[1]
#         #     if increment == -1:
#         #         first_visible_tile = camera_view.bottom // TILE_SIZE
#         #     elif increment == 1:
#         #         first_visible_tile = camera_view.top // TILE_SIZE

#         # if horizontal:
#         #     first_tile_in_line = self._start_coordinates[0]
#         # else:
#         #     first_tile_in_line = self._start_coordinates[1]

#         # step = tile_count

#         # for origin in range(tile_count):
#         #     if increment == -1:
#         #         max_tile_coordinate = min(first_visible_tile, first_tile_in_line)
#         #         tile_coordinate = greatest_multiple(origin, step, max_tile_coordinate)
#         #     elif increment == 1:
#         #         min_tile_coordinate = max(first_visible_tile, first_tile_in_line)
#         #         tile_coordinate = least_multiple(origin, step, min_tile_coordinate)

#         #     if horizontal:
#         #         coordinates = self._start_coordinates[0], tile_coordinate
#         #     else:
#         #         coordinates = tile_coordinate, self._start_coordinates[1]

#         #     if horizontal:
#         #         if increment == -1:
#         #             index = origin - tile_coordinate
#         #         elif increment == 1:
#         #             index = tile_coordinate - origin
#         #     else:
#         #     image = self._tile_images[self._choose_tile(index)]
#         #     tile = Tile(coordinates, image)
#         #     surface.blit(tile.image, tile.rect)

#         # camera_view = self._camera.rect_view()
#         # if horizontal:
#         #     tile_count = math.ceil(WIDTH / TILE_SIZE)
#         # else:
#         #     tile_count = math.ceil(HEIGHT / TILE_SIZE)
#         # step = tile_count

#         # for origin in range(tile_count):
#         #     if self._increment[0] == -1:
#         #         rightmost_visible_tile = camera_view.right // TILE_SIZE
#         #         first_tile_in_line = self._start_coordinates[0]
#         #         max_tile_x = min(rightmost_visible_tile, first_tile_in_line)
#         #         x = greatest_multiple(origin, step, max_tile_x)
#         #         tile_coordinates = x, self._start_coordinates[1]
#         #         index = self._start_coordinates[0] - x
#         #     elif self._increment[0] == 1:
#         #         leftmost_visible_tile = camera_view.left // TILE_SIZE
#         #         first_tile_in_line = self._start_coordinates[0]
#         #         min_tile_x = max(leftmost_visible_tile, first_tile_in_line)
#         #         x = least_multiple(origin, step, min_tile_x)
#         #         tile_coordinates = x, self._start_coordinates[1]
#         #         index = x - self._start_coordinates[0]
#         #     elif self._increment[1] == -1:
#         #         lowest_visible_tile = camera_view.bottom // TILE_SIZE
#         #         first_tile_in_line = self._start_coordinates[1]
#         #         max_tile_y = min(lowest_visible_tile, first_tile_in_line)
#         #         y = greatest_multiple(origin, step, max_tile_y)
#         #         tile_coordinates = self._start_coordinates[0], y
#         #         index = self._start_coordinates[1] - y
#         #     elif self._increment[1] == 1:
#         #         highest_visible_tile = camera_view.top // TILE_SIZE
#         #         first_tile_in_line = self._start_coordinates[1]
#         #         min_tile_y = max(highest_visible_tile, first_tile_in_line)
#         #         y = least_multiple(origin, step, min_tile_y)
#         #         tile_coordinates = self._start_coordinates[0], y
#         #         index = y - self._start_coordinates[1]

#         #     image = self._tile_images[self._choose_tile(index)]
#         #     tile = Tile(tile_coordinates, image)
#         #     surface.blit(tile.image, tile.rect)

#         if self._increment == (-1, 0):
#             min_tile_x = self._camera.rect_view().left // TILE_SIZE
#             if self._start_coordinates[0] >= min_tile_x:
#                 max_tile_x = self._camera.rect_view().right // TILE_SIZE
#                 max_tile_x = min(max_tile_x, self._start_coordinates[0])
#                 for x in range(min_tile_x, max_tile_x + 1):
#                     coordinates = x, self._start_coordinates[1]
#                     relative_i = self._start_coordinates[0] - x
#                     image = self._tile_images[self._choose_tile(relative_i)]
#                     tile = Tile(coordinates, image)
#                     surface.blit(tile.image, tile.rect)
#         elif self._increment == (1, 0):
#             max_tile_x = self._camera.rect_view().right // TILE_SIZE
#             if self._start_coordinates[0] <= max_tile_x:
#                 min_tile_x = self._camera.rect_view().left // TILE_SIZE
#                 min_tile_x = max(min_tile_x, self._start_coordinates[0])
#                 for x in range(min_tile_x, max_tile_x + 1):
#                     coordinates = x, self._start_coordinates[1]
#                     relative_i = x - self._start_coordinates[0]
#                     image = self._tile_images[self._choose_tile(relative_i)]
#                     tile = Tile(coordinates, image)
#                     surface.blit(tile.image, tile.rect)
#         elif self._increment == (0, -1):
#             min_tile_y = self._camera.rect_view().top // TILE_SIZE
#             if self._start_coordinates[1] >= min_tile_y:
#                 max_tile_y = self._camera.rect_view().bottom // TILE_SIZE
#                 max_tile_y = min(max_tile_y, self._start_coordinates[1])
#                 for y in range(min_tile_y, max_tile_y + 1):
#                     coordinates = self._start_coordinates[0], y
#                     relative_i = self._start_coordinates[1] - y
#                     image = self._tile_images[self._choose_tile(relative_i)]
#                     tile = Tile(coordinates, image)
#                     surface.blit(tile.image, tile.rect)
#         elif self._increment == (0, 1):
#             max_tile_y = self._camera.rect_view().bottom // TILE_SIZE
#             if self._start_coordinates[1] <= max_tile_y:
#                 min_tile_y = self._camera.rect_view().top // TILE_SIZE
#                 min_tile_y = max(min_tile_y, self._start_coordinates[1])
#                 for y in range(min_tile_y, max_tile_y + 1):
#                     coordinates = self._start_coordinates[0], y
#                     relative_i = y - self._start_coordinates[1]
#                     image = self._tile_images[self._choose_tile(relative_i)]
#                     tile = Tile(coordinates, image)
#                     surface.blit(tile.image, tile.rect)

#         # if self._increment[0] == -1:
#         #     min_tile_x = camera_view.left // TILE_SIZE
#         #     if self._start_coordinates[0] >= min_tile_x:
#         #         max_tile_x = camera_view.right // TILE_SIZE
#         #         max_tile_x = min(max_tile_x, self._start_coordinates[0])
#         #         first_tile_coordinates = max_tile_x, self._start_coordinates[1]
#         #         length = max_tile_x - min_tile_x + 1
#         #         self._draw_line_of_tiles(surface, first_tile_coordinates, length)
#         # elif self._increment[0] == 1:
#         #     max_tile_x = camera_view.left // TILE_SIZE
#         #     if self._start_coordinates[0] >= max_tile_x:
#         #         min_tile_x = camera_view.right // TILE_SIZE
#         #         min_tile_x = max(min_tile_x, self._start_coordinates[0])
#         #         first_tile_coordinates = min_tile_x, self._start_coordinates[1]
#         #         length = max_tile_x - min_tile_x + 1
#         #         self._draw_line_of_tiles(surface, first_tile_coordinates, length)
#         # elif self._increment[1] == -1:
#         #     pass
#         # elif self._increment[1] == 1:
#         #     pass

#         # if horizontal:
#         #     tile_count = math.ceil(WIDTH / TILE_SIZE)
#         #     step = tile_count
#         #     for origin in range(tile_count):
#         #         if self._increment[0] == -1:
#         #             rightmost_visible_tile = self._camera.rect_view().right // TILE_SIZE
#         #             max_tile_x = min(rightmost_visible_tile, self._start_coordinates[0])
#         #             x = greatest_multiple(origin, step, max_tile_x)
#         #             index = x - origin
#         #         elif self._increment[0] == 1:
#         #             min_value_pixels = self._camera.rect_view().
#         # else:
#         #     tile_count = math.ceil(HEIGHT / TILE_SIZE)
#         #     start = self._start_coordinates[1]
#         #     step = self._start_coordinates[1]

#         # image = self._tile_images[self._choose_tile(index)]
#         # tile = Tile((x, self._increment[1]), image)
#         # surface.blit(tile.image, tile.rect)

#     # def _draw_line_of_tiles(self, surface, first_tile_coordinates, length):
#     #     tile_coordinates = first_tile_coordinates

#     #     for relative_index in range(length):
#     #         image = self._tile_images[self._choose_tile(relative_index)]
#     #         tile = Tile(tile_coordinates, image)
#     #         surface.blit(tile.image, tile.rect)
#     #         tile_coordinates = (
#     #             tile_coordinates[0] + self._increment[0],
#     #             tile_coordinates[1] + self._increment[1]
#     #         )

#     # def _draw_tile(self, first_tile_coordinates, relative_index):
#     #     tile_coordinates = first_tile_coordinates
#     #     for i in range(relative_index - 1):
#     #         tile_coordinates = (
#     #             tile_coordinates[0] + self._increment[0],
#     #             tile_coordinates[1] + self._increment[1]
#     #         )
#     #     image = self._choose_tile(relative_index)
#     #     tile = Tile(tile_coordinates, image)
#     #     surface.blit(tile.image, tile.rect)


class EndlessGridOfTilesRenderer:
    def __init__(
        self, start, increment_x, increment_y, camera, tile_images_dict,
        func_choose_tile=None
    ):
        self._start_coordinates = start
        self._increment_x = increment_x
        self._increment_y = increment_y
        self._camera = camera
        self._tile_images = tile_images_dict

        if func_choose_tile is not None:
            self._choose_tile = func_choose_tile
        else:
            self._choose_tile = lambda x, y: next(iter(self._tile_images))

    def draw(self, surface):
        row_of_columns_coordinates = compute_line_of_tiles_coordinates(
            self._start_coordinates, (self._increment_x, 0), self._camera
        )
        for relative_x, coordinates in row_of_columns_coordinates:
            choose_tile = functools.partial(self._choose_tile, relative_x)
            EndlessLineOfTilesRenderer(
                coordinates, (0, self._increment_y), self._camera,
                self._tile_images, choose_tile
            ).draw(surface)


class EndlessLineOfTilesRenderer:
    def __init__(
        self, start, increment, camera, tile_images_dict, func_choose_tile=None
    ):
        self._start_coordinates = start
        self._increment = increment
        self._camera = camera
        self._tile_images = tile_images_dict

        if func_choose_tile is not None:
            self._choose_tile = func_choose_tile
        else:
            self._choose_tile = lambda i: next(iter(self._tile_images))

    def draw(self, surface):
        tiles_coordinates = compute_line_of_tiles_coordinates(
            self._start_coordinates, self._increment, self._camera
        )
        for relative_i, coordinates in tiles_coordinates:
            image = self._tile_images[self._choose_tile(relative_i)]
            tile = Tile(coordinates, image)
            surface.blit(tile.image, tile.rect)


def compute_line_of_tiles_coordinates(start_coordinates, increment, camera):
    tiles_coordinates = []
    if increment == (-1, 0):
        min_tile_x = camera.rect_view().left // TILE_SIZE
        if start_coordinates[0] >= min_tile_x:
            max_tile_x = camera.rect_view().right // TILE_SIZE
            max_tile_x = min(max_tile_x, start_coordinates[0])
            for x in range(min_tile_x, max_tile_x + 1):
                coordinates = x, start_coordinates[1]
                relative_i = start_coordinates[0] - x
                tiles_coordinates.append((relative_i, coordinates))
    elif increment == (1, 0):
        max_tile_x = camera.rect_view().right // TILE_SIZE
        if start_coordinates[0] <= max_tile_x:
            min_tile_x = camera.rect_view().left // TILE_SIZE
            min_tile_x = max(min_tile_x, start_coordinates[0])
            for x in range(min_tile_x, max_tile_x + 1):
                coordinates = x, start_coordinates[1]
                relative_i = x - start_coordinates[0]
                tiles_coordinates.append((relative_i, coordinates))
    elif increment == (0, -1):
        min_tile_y = camera.rect_view().top // TILE_SIZE
        if start_coordinates[1] >= min_tile_y:
            max_tile_y = camera.rect_view().bottom // TILE_SIZE
            max_tile_y = min(max_tile_y, start_coordinates[1])
            for y in range(min_tile_y, max_tile_y + 1):
                coordinates = start_coordinates[0], y
                relative_i = start_coordinates[1] - y
                tiles_coordinates.append((relative_i, coordinates))
    elif increment == (0, 1):
        max_tile_y = camera.rect_view().bottom // TILE_SIZE
        if start_coordinates[1] <= max_tile_y:
            min_tile_y = camera.rect_view().top // TILE_SIZE
            min_tile_y = max(min_tile_y, start_coordinates[1])
            for y in range(min_tile_y, max_tile_y + 1):
                coordinates = start_coordinates[0], y
                relative_i = y - start_coordinates[1]
                tiles_coordinates.append((relative_i, coordinates))
    return tiles_coordinates


class Door(pygame.sprite.Sprite):
    def __init__(self, destination_level, start):
        super().__init__()

        if start:
            self.image = load_image('door_closed.png')
        else:
            self.image = load_image('door_closed_finish.png')
        self._open_door_image = load_image('door_open.png')
        self.rect = self.image.get_rect()
        self.destination_level = destination_level
        self.start = start

    def open(self):
        self.image = self._open_door_image


class MovingPlatform(pygame.sprite.Sprite):
    def __init__(self, tiles_str, tile_destinations):
        super().__init__()

        self._destinations = []
        for tile_coordinates in tile_destinations:
            x = tile_coordinates[0] * TILE_SIZE
            y = (tile_coordinates[1] + 1) * TILE_SIZE
            self._destinations.append((x, y))
        self._next_destination_index = 0

        width = tiles_str.find('\n') * TILE_SIZE
        height = tiles_str.count('\n') * TILE_SIZE
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.bottomleft = self._destinations[0]

        self.image = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        tiles = tiles_from_str(tiles_str)
        tiles.draw(self.image)

        self.last_move = 0, 0

    def update(self):
        next_destination = self._destinations[self._next_destination_index]

        if self.rect.left > next_destination[0]:
            self.last_move = -1, 0
        elif self.rect.left < next_destination[0]:
            self.last_move = 1, 0
        if self.rect.bottom > next_destination[1]:
            self.last_move = 0, -1
        elif self.rect.bottom < next_destination[1]:
            self.last_move = 0, 1
        self.rect.move_ip(self.last_move)

        if self.rect.bottomleft == next_destination:
            self._next_destination_index += 1
            if self._next_destination_index >= len(self._destinations):
                self._next_destination_index = 0


@dataclasses.dataclass
class LevelCompletion:
    level_number: int
    completed: bool


# class FontRenderer:
#     def __init__(self, font_name):
#         self._characters = (
#             r""" !"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNO"""
#             r"""PQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}~"""
#         )
#         images = load_images(font_name)
#         for image in images:
#             if font_name == 'font2':
#                 image.set_colorkey((0, 0, 0))
#             image.lock()
#             width, height = image.get_size()
#             for x in range(width):
#                 for y in range(height):
#                     if image.get_at((x, y)) == pygame.Color(255, 255, 255):
#                         image.set_at((x, y), pygame.Color(234, 255, 242))
#                     if (
#                         font_name == 'font'
#                         and image.get_at((x, y)) == pygame.Color(0, 0, 0)
#                     ):
#                         image.set_at((x, y), pygame.Color(39, 32, 52))
#             image.unlock()
#         self._images = {}
#         for character, image in zip(self._characters, images):
#             self._images[character] = image
#         self._character_width = images[0].get_width()

#     def draw(self, surface, position, text):
#         for i, character in enumerate(text):
#             if character != ' ' and character in self._characters:
#                 image = self._images[character]
#                 kerning = -1
#                 x = position[0] + i * (self._character_width + kerning)
#                 y = position[1]
#                 surface.blit(image, (x, y))


class FontRenderer:
    def __init__(self):
        self._characters = (
            r""" !"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNO"""
            r"""PQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}~"""
        )

        images = load_images('font')
        for image in images:
            image.lock()
            width, height = image.get_size()
            for x in range(width):
                for y in range(height):
                    if image.get_at((x, y)) == pygame.Color(255, 255, 255):
                        image.set_at((x, y), pygame.Color(234, 255, 242))
                    if image.get_at((x, y)) == pygame.Color(0, 0, 0):
                        image.set_at((x, y), pygame.Color(39, 32, 52))
            image.unlock()
        self._images = {}
        for character, image in zip(self._characters, images):
            self._images[character] = image

        self._character_widths = {}
        fontdef_file = open('assets/font/fontdef.txt', encoding='utf-8')
        for line in fontdef_file:
            character = line[0]
            width = line[2:-1]
            self._character_widths[character] = int(width)
        self._character_height = images[0].get_height()
        self._kerning = -1

    def calculate_rect(self, text):
        width = 0
        for character in text:
            if character not in self._characters:
                character = ' '
            width += self._character_widths[character] + self._kerning
        return pygame.Rect(0, 0, width, self._character_height)

    def draw(self, surface, position, text):
        x = position[0]
        y = position[1]
        for character in text:
            if character not in self._characters:
                character = ' '
            if character != ' ':
                image = self._images[character]
                surface.blit(image, (x, y))
            x += self._character_widths[character] + self._kerning


class FontRenderer2:
    def __init__(self):
        self._characters = (
            r""" !"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNO"""
            r"""PQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}~"""
        )

        images = load_images('font2')
        for image in images:
            image.set_colorkey((0, 0, 0))
            image.lock()
            width, height = image.get_size()
            for x in range(width):
                for y in range(height):
                    if image.get_at((x, y)) == pygame.Color(255, 255, 255):
                        image.set_at((x, y), pygame.Color(234, 255, 242))
            image.unlock()
        self._images = {}
        for character, image in zip(self._characters, images):
            self._images[character] = image

        self._character_width = images[0].get_width()
        self._character_height = images[0].get_height()
        self._kerning = -1

    def calculate_rect(self, text):
        width = len(text) * (self._character_width + self._kerning)
        return pygame.Rect(0, 0, width, self._character_height)

    def draw(self, surface, position, text):
        for i, character in enumerate(text):
            if character in self._characters:
                image = self._images[character]
                x = position[0] + i * (self._character_width + self._kerning)
                y = position[1]
                surface.blit(image, (x, y))


_images = {}


def load_image(name):
    if name not in _images:
        full_name = os.path.join('assets', name)
        try:
            image = pygame.image.load(full_name)
            if image.get_alpha() is None:
                image = image.convert()
            else:
                image = image.convert_alpha()
        except pygame.error as e:
            print('Cannot load image: ', full_name)
            raise SystemExit from e
        _images[name] = image
    return _images[name]


def load_images(dir_name):
    images = []
    full_dir_name = os.path.join('assets', dir_name)
    files = [os.path.join(full_dir_name, f) for f in os.listdir(full_dir_name)]
    regular_files = filter(os.path.isfile, files)
    image_files = filter(lambda f: f.endswith('.png'), regular_files)
    for image_file in sorted(image_files):
        images.append(load_image(image_file[7:]))
    return images


if __name__ == '__main__':
    main()
