import dataclasses
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
        self.hitbox = pygame.Rect(0, 0, 15, 22)
        self.hitbox.midbottom = midbottom
        self.rect = self.image.get_rect()
        self._update_rect()
        self.alive = True
        self.entered_door = None
        self.slashes = pygame.sprite.Group()

        self._level = level

        self._g = 0.33

        self._v0 = 0
        self._y0 = self.hitbox.y
        self._t = 0

        self._platforms_standing_on = self._get_platforms_standing_on()

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
        if action != 'die':
            crushed = self._adjust_postition_for_moving_platforms()

        if (
            action not in ('die', 'door')
            and (pressed_keys[pygame.K_q] or crushed)
        ):
            action = 'die'
            self._die()

        door_to_walk_in = self.choose_door_to_walk_in()
        if (
            not action and self._on_ground() and pressed_keys[pygame.K_e]
            and door_to_walk_in
        ):
            action = 'door'
            self._door(door_to_walk_in)

        if not action and self._on_ground() and pressed_buttons[0]:
            action = 'slash'
            self._slash()

        if not action and self._on_ground() and pressed_keys[pygame.K_w]:
            self._jump(6)

        self._t += 1
        y = round(self._y0 - self._v0 * self._t + self._g * self._t ** 2 / 2)

        walk_movement_x = 0
        if not action:
            speed = 3
            if pressed_keys[pygame.K_a]:
                walk_movement_x -= speed
            if pressed_keys[pygame.K_d]:
                walk_movement_x += speed
        if walk_movement_x:
            self._flip = walk_movement_x < 0
        x = self.hitbox.x + walk_movement_x

        if action != 'die':
            self._move((x, y))
        else:
            self.hitbox.topleft = x, y

        self._platforms_standing_on = self._get_platforms_standing_on()

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

    def _adjust_postition_for_moving_platforms(self):
        adjustment = self._get_position_adjustment_for_platforms_standing_on()
        self.hitbox.move_ip(adjustment)
        if adjustment[1] != 0:
            self._reset_jump()
        crushed = self._uncollide(adjustment)
        return crushed

    def _uncollide(self, last_move):
        hittable_objects = self._level.get_hittable_objects()
        old_y = self.hitbox.y
        crushed = uncollide_rect(self.hitbox, last_move, hittable_objects)
        if self.hitbox.y != old_y:
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
        return self._filter_sprites_standing_on(self._level.moving_platforms)

    def _on_ground(self):
        hittable_objects = self._level.get_hittable_objects()
        return bool(self._filter_sprites_standing_on(hittable_objects))

    def _filter_sprites_standing_on(self, group):
        colliding_sprites = self._collide(group)
        self.hitbox.y += 1
        sprites = self._collide(group)
        self.hitbox.y -= 1

        sprites_standing_on = []
        if self._y0 == self.hitbox.y and self._v0 == 0:
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

    def _die(self):
        self._jump(3)

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
        elif self._on_ground():
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
            instantaneous_speed_y = -self._v0 + self._g * self._t
            if instantaneous_speed_y <= 0:
                self.image = self._animation[0]
            else:
                self.image = self._animation[1]

        if self._flip:
            self.image = pygame.transform.flip(self.image, True, False)

    def _jump(self, speed):
        self._v0 = speed
        self._y0 = self.hitbox.y
        self._t = 0

    def _reset_jump(self):
        self._v0 = 0
        self._y0 = self.hitbox.y
        self._t = 0

    def _move(self, new_pos):
        move(self.hitbox, new_pos, self._level.get_hittable_objects())
        if self.hitbox.y != new_pos[1]:
            self._reset_jump()

    def _update_rect(self):
        offset = (-9, -10) if not self._flip else (-8, -10)
        self.rect.topleft = self.hitbox.topleft
        self.rect.move_ip(offset)


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


def move(rect, new_pos, tiles):
    move_x(rect, new_pos[0], tiles)
    move_y(rect, new_pos[1], tiles)


def move_x(rect, new_x, tiles):
    old_x = rect.x
    rect.x = new_x
    hit_list = rectcollide(rect, tiles)
    if rect.x < old_x:
        uncollide(rect, hit_list, 'left')
    elif rect.x > old_x:
        uncollide(rect, hit_list, 'right')


def move_y(rect, new_y, tiles):
    old_y = rect.y
    rect.y = new_y
    hit_list = rectcollide(rect, tiles)
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
    tiles: pygame.sprite.Group
    doors: pygame.sprite.Group
    snakes: pygame.sprite.Group
    moving_platforms: pygame.sprite.Group
    water_level: int

    def get_hittable_objects(self):
        hittable_objects = pygame.sprite.Group()
        hittable_objects.add((self.tiles, self.moving_platforms))
        return hittable_objects


def create_level(level_number):
    level_data = levels.get_level_data(level_number)

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

    return Level(tiles, doors, snakes, moving_platforms, water_level)


@dataclasses.dataclass
class World:
    level: Level
    player: Player
    door_text_viewer: DoorTextViewer
    water_tiles: pygame.sprite.Group


def create_world(level_number, prev_level_number, level_completions, camera):
    level = create_level(level_number)
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
        tile = WaterTileTop('w3', tile_coordinates, tile_count, camera)
        water_tiles.add(tile)

    tile_count_horizontal = tile_count
    tile_count_horizontal = ceil_base(tile_count_horizontal, base=2)
    tile_count_vertical = math.ceil(HEIGHT / TILE_SIZE) + 1
    tile_count_vertical = ceil_base(tile_count_vertical, base=2)
    for tile_x in range(tile_count_horizontal):
        for tile_y in range(tile_count_vertical):
            tile_type = '00'
            if tile_y % 2 == tile_x % 2:
                tile_type = 'w0'
            tile_coordinates = tile_x, tile_water_level + 1 + tile_y
            tile_counts = tile_count_horizontal, tile_count_vertical
            tile = WaterTileMiddle(
                tile_type, tile_coordinates, *tile_counts, camera
            )
            water_tiles.add(tile)

    return water_tiles


def ceil_base(x, base=1):
    return math.ceil(x / base) * base


class Tile(pygame.sprite.Sprite):
    def __init__(self, tile_type, tile_coordinates):
        super().__init__()

        self.image = load_image(tile_type + '.png')
        self.rect = self.image.get_rect()
        self.rect.x = tile_coordinates[0] * TILE_SIZE
        self.rect.y = tile_coordinates[1] * TILE_SIZE


class WaterTileTop(Tile):
    def __init__(self, tile_type, tile_coordinates, tile_count, camera):
        super().__init__(tile_type, tile_coordinates)

        self._camera = camera
        self._right_start = self.rect.right
        self._right_step = tile_count * TILE_SIZE

    def update(self):
        view = self._camera.rect_view()
        right = least_multiple(self._right_start, self._right_step, view.x + 1)
        self.rect.right = right


class WaterTileMiddle(WaterTileTop):
    def __init__(
        self, tile_type, tile_coordinates, tile_count_horizontal,
        tile_count_vertical, camera
    ):
        super().__init__(
            tile_type, tile_coordinates, tile_count_horizontal, camera
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


def least_multiple(origin, step, min_value):
    return origin + math.ceil((min_value - origin) / step) * step


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

        width = tiles_str.find('\n') // 2 * TILE_SIZE
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


def tiles_from_str(string):
    tiles = pygame.sprite.Group()
    for y, line in enumerate(string.splitlines()):
        for i in range(0, len(line) - 1, 2):
            tile_type = line[i:i+2]
            if not tile_type == '--':
                tiles.add(Tile(tile_type, (i // 2, y)))
    return tiles


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
